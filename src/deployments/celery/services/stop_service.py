"""
deployments/celery/services/stop_service.py
-------------------------------------------
Container stop service.

Key changes vs. legacy:
  * Acquires the per-service advisory lock so a stop cannot race with
    an in-progress deploy for the same Service.
  * Uses the unified ``InvalidServiceStateError`` from
    ``deployments.common.exceptions``.
  * Removes stopped containers after a successful stop so they don't
    accumulate on disk (legacy code only stopped, never removed —
    operators had to manually prune).  This is gated by a
    ``DEPLOYMENT_REMOVE_STOPPED_CONTAINERS`` setting (default True).
"""
from __future__ import annotations

import logging

from django.db import transaction

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deployments.core.deploy import Deploy as DeployFacade
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import SwarmRuntime, swarm_enabled
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.core.state.manager import StateManager
from deployments.common.exceptions import InvalidServiceStateError
from services.models import Service
from services.revisioning import get_active_deploy
from deployments.infrastructure.django_runtime import DjangoRuntimeSelectionResolver
from deployments.reconciliation import (
    DesiredRuntimeState,
    ReconciliationAction,
    ReconciliationDecision,
    ReconciliationExecutionContext,
    ReconciliationExecutor,
)
from deployments.runtime.contract import RuntimeHandle
from deployments.runtime.contract import RuntimeIdentity

from ..service_status import ServiceStateManager
from ..waiters import ContainerWaiter

logger = logging.getLogger(__name__)


def _should_remove_stopped_containers() -> bool:
    try:
        from django.conf import settings  # type: ignore
        return bool(getattr(settings, "DEPLOYMENT_REMOVE_STOPPED_CONTAINERS", True))
    except Exception:
        return True


class StopService:
    """Stop the complete runtime workload without misreporting deploy failures."""

    @staticmethod
    def _transition_if_current_generation(
        service_id: int,
        target: str,
        *,
        expected_lifecycle_generation: int | str,
        update_fields: dict | None = None,
    ) -> bool:
        with transaction.atomic():
            service = (
                Service.objects.select_for_update()
                .filter(pk=service_id)
                .first()
            )
            if service is None:
                return False
            actual_generation = int(service.lifecycle_generation or 0)
            if str(actual_generation) != str(expected_lifecycle_generation):
                logger.info(
                    "Skipping stale stop state projection for service %s: expected generation=%s actual=%s.",
                    service_id, expected_lifecycle_generation, actual_generation,
                )
                return False
            if service.status != SERVICE_STATUS_CHOICES.STOPPING:
                return service.status == target
            StateManager.transition_service(service_id, target, update_fields=update_fields)
            return True

    def _restore_observed_state_after_failure(
        self,
        service_id: int,
        container_name: str,
        *,
        expected_lifecycle_generation: int | str,
    ) -> None:
        """Align the Service projection with observed runtime; unknown stays STOPPING."""
        try:
            if swarm_enabled():
                backend = SwarmRuntime()
                names = backend.service_names_for_service(str(service_id))
                states = [backend.inspect_service(name) for name in names]
                if any(
                    state is not None and int(state.replicas_running or 0) > 0
                    for state in states
                ):
                    target = SERVICE_STATUS_CHOICES.RUNNING
                elif all(
                    state is None
                    or (
                        int(state.replicas_desired or 0) == 0
                        and int(state.replicas_running or 0) == 0
                    )
                    for state in states
                ):
                    target = SERVICE_STATUS_CHOICES.STOPPED
                else:
                    logger.warning(
                        "Swarm still desires replicas for service %s but none are running; keeping STOPPING.",
                        service_id,
                    )
                    return
            else:
                target = (
                    SERVICE_STATUS_CHOICES.RUNNING
                    if Container.container_is_running(container_name)
                    else SERVICE_STATUS_CHOICES.STOPPED
                )
        except Exception:
            logger.warning(
                "Could not inspect service %s after stop failure; keeping STOPPING instead of guessing.",
                service_id, exc_info=True,
            )
            return

        self._transition_if_current_generation(
            service_id,
            target,
            expected_lifecycle_generation=expected_lifecycle_generation,
            update_fields={"desired_state": "stopped"},
        )

    def execute(
        self,
        service_id: int,
        *,
        expected_lifecycle_generation: int | str | None = None,
    ) -> None:
        try:
            with acquire_service_deployment_lock(service_id):
                self._execute_locked(
                    service_id,
                    expected_lifecycle_generation=expected_lifecycle_generation,
                )
        except InvalidServiceStateError as exc:
            logger.info("Skipped stop execution for service ID %s: %s", service_id, str(exc))
            return
        except Exception:
            # Propagate runtime errors so Celery can retry; swallowing them
            # made failed stop tasks appear successful.
            logger.exception("Stop for service %s failed.", service_id)
            raise

    def _execute_locked(
        self,
        service_id: int,
        *,
        expected_lifecycle_generation: int | str | None = None,
    ) -> None:
        if expected_lifecycle_generation is not None:
            current = (
                Service.objects.filter(pk=service_id)
                .values("lifecycle_generation", "desired_state", "status")
                .first()
            )
            if current is None:
                logger.info("Skipping stale stop for missing service %s.", service_id)
                return
            actual_generation = int(current.get("lifecycle_generation") or 0)
            if str(actual_generation) != str(expected_lifecycle_generation):
                logger.info(
                    "Skipping stale stop for service %s: expected lifecycle generation=%s actual=%s.",
                    service_id, expected_lifecycle_generation, actual_generation,
                )
                return
            if str(current.get("desired_state") or "").lower() != "stopped":
                logger.info(
                    "Skipping stale stop for service %s: desired_state is now %s.",
                    service_id, current.get("desired_state"),
                )
                return

        try:
            service = ServiceStateManager.lock_and_start_stopping(service_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped stop execution for service ID %s: %s", service_id, str(exc))
            return

        # HTTP normally fences desired_state before this worker. Direct task
        # calls remain safe without incrementing an existing stop intent.
        from services.lifecycle import bump_lifecycle
        from services.lifecycle.fencing import capture_generation
        if str(service.desired_state or "").lower() != "stopped":
            generation = bump_lifecycle(service.pk, desired_state="stopped")
        else:
            generation = capture_generation(service)
        service.desired_state = "stopped"
        service.lifecycle_generation = generation

        container_name = service.get_docker_service_name()
        active_deploy = get_active_deploy(service)
        stopped = False

        try:
            if swarm_enabled():
                resolver = DjangoRuntimeSelectionResolver()
                selection = resolver.resolve(
                    service=service,
                    revision=getattr(service, "active_revision", None),
                    deployment=active_deploy,
                    probe=True,
                )
                runtime = resolver.registry.resolve_adapter(selection)
                backend_runtime = getattr(runtime, "runtime", None)

                resource_name = container_name
                resource_id = None
                process_name = "web"

                if (
                    backend_runtime is not None
                    and hasattr(backend_runtime, "service_names_for_service")
                    and hasattr(backend_runtime, "inspect_service")
                ):
                    names = backend_runtime.service_names_for_service(str(service.pk))
                    observed = []
                    for name in names:
                        row = backend_runtime.inspect_service(name)
                        if row is not None and (
                            int(row.replicas_desired or 0) > 0
                            or int(row.replicas_running or 0) > 0
                        ):
                            observed.append((name, row))
                    if not observed:
                        logger.info(
                            "Swarm service group for %s is already stopped or absent.",
                            service_id,
                        )
                        stopped = True
                    else:
                        selected_name, selected_state = next(
                            (item for item in observed if item[0] == container_name),
                            observed[0],
                        )
                        resource_name = selected_name
                        resource_id = str(selected_state.service_id or "")
                        process_name = str(
                            (selected_state.labels or {}).get("passdeployer.process")
                            or "web"
                        )
                else:
                    identity = RuntimeIdentity(
                        service_id=str(service.pk),
                        deployment_id=str(getattr(active_deploy, "pk", "") or "") or None,
                        revision_id=str(getattr(getattr(service, "active_revision", None), "pk", "") or "") or None,
                        process_name="web",
                        runtime_name=container_name,
                    )
                    observation = runtime.inspect(identity)
                    if observation.status.value in {"missing", "stopped"}:
                        stopped = True
                    else:
                        resource_id = str(observation.runtime_id or "")

                if not stopped:
                    identity = RuntimeIdentity(
                        service_id=str(service.pk),
                        deployment_id=str(getattr(active_deploy, "pk", "") or "") or None,
                        revision_id=str(getattr(getattr(service, "active_revision", None), "pk", "") or "") or None,
                        process_name=process_name,
                        runtime_name=resource_name,
                    )
                    handle = RuntimeHandle(
                        backend=selection.backend,
                        identity=identity,
                        runtime_id=str(resource_id or ""),
                        resource_name=resource_name,
                    )
                    desired = DesiredRuntimeState(
                        service_id=str(service.pk),
                        revision_id=str(getattr(getattr(service, "active_revision", None), "pk", "") or "") or None,
                        desired_state="stopped",
                        runtime_name=resource_name,
                    )
                    decision = ReconciliationDecision(
                        action=ReconciliationAction.STOP,
                        reason_code="stop_requested",
                        message="Service desired state is stopped.",
                        service_id=desired.service_id,
                        runtime_name=desired.runtime_name,
                    )
                    context = ReconciliationExecutionContext(
                        service_id=str(service.pk),
                        lifecycle_generation=generation,
                        active_revision_id=desired.revision_id,
                        owns_execution=lambda sid=str(service.pk), gen=generation: bool(
                            Service.objects.filter(pk=sid, lifecycle_generation=gen).exists()
                        ),
                        current_generation=lambda sid=str(service.pk): Service.objects.filter(
                            pk=sid
                        ).values_list("lifecycle_generation", flat=True).first(),
                    )
                    ReconciliationExecutor().execute(
                        decision,
                        desired=desired,
                        selection=selection,
                        runtime=runtime,
                        context=context,
                        handle=handle,
                    )
                    stopped = (
                        backend_runtime.wait_service_group_stopped(
                            str(service_id), timeout=30.0
                        )
                        if backend_runtime is not None
                        and hasattr(backend_runtime, "wait_service_group_stopped")
                        else True
                    )
                    if not stopped:
                        raise TimeoutError(
                            f"Swarm service group {service_id} still has running tasks after the stop timeout."
                        )
            else:
                if Container.container_is_running(container_name):
                    logger.info("Dispatching stop request for container: %s", container_name)
                    DeployFacade.stop_container(container_name)
                    ContainerWaiter.wait_until_stopped(container_name, timeout=10)
                else:
                    logger.info(
                        "Container %s already matches terminal state: STOPPED.",
                        container_name,
                    )

                if _should_remove_stopped_containers():
                    try:
                        stopped_container = Container(container_name)
                        if stopped_container.exists():
                            stopped_container.remove()
                            logger.info("Removed stopped container '%s' to free disk.", container_name)
                    except Exception as cleanup_exc:
                        logger.warning(
                            "Failed to remove stopped container '%s': %s. Container remains stopped but on disk.",
                            container_name, cleanup_exc,
                        )
                stopped = True

            if stopped:
                self._transition_if_current_generation(
                    service_id,
                    SERVICE_STATUS_CHOICES.STOPPED,
                    expected_lifecycle_generation=generation,
                    update_fields={"desired_state": "stopped"},
                )
        except Exception as exc:
            logger.error(
                "Stop execution runtime failure on %s: %s",
                container_name, str(exc), exc_info=True,
            )
            self._restore_observed_state_after_failure(
                service_id,
                container_name,
                expected_lifecycle_generation=generation,
            )
            raise
