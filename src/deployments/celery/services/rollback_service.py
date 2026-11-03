"""Release-based rollback execution through the shared deployment lifecycle."""

from __future__ import annotations

from copy import copy
from dataclasses import replace
import logging

from django.db import transaction
from django.utils import timezone

from deploy.models import Deploy, Release, RollbackStatusChoices
from deployments.application.context import DeploymentExecutionContext
from deployments.application.lifecycle import DeploymentLifecycleExecutor
from deployments.application.strategies import CallbackDeploymentStrategy
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.core.state.manager import StateManager
from deployments.infrastructure.django_lifecycle import DjangoDeploymentLifecycleStore
from deployments.infrastructure.django_runtime import DjangoRuntimeSelectionResolver
from deployments.common.exceptions import DeploymentError, InvalidServiceStateError
from deployments.runtime.contract import RuntimeBackend
from services.lifecycle.authority import get_authoritative_deploy
from services.models import Service

logger = logging.getLogger(__name__)


class ReleaseRollbackService:
    """Promote a known-good immutable Release using the normal runtime contract."""

    def execute(
        self,
        deployment_id: int | str,
        *,
        task_id: str,
        expected_lifecycle_generation: int,
        expected_previous_deploy_id: str,
        allow_owned_retry: bool = False,
    ) -> None:
        deploy_row = (
            Deploy.objects.select_related("service")
            .filter(pk=deployment_id)
            .first()
        )
        if deploy_row is None:
            logger.warning("Rollback attempt %s no longer exists.", deployment_id)
            return

        service_id = deploy_row.service_id
        with acquire_service_deployment_lock(service_id) as deployment_lock:
            claimed = StateManager.lock_and_get_deployment(
                int(deploy_row.pk),
                task_id=str(task_id),
                allow_owned_retry=allow_owned_retry,
            )
            if claimed is None:
                logger.info("Rollback attempt %s was not claimable.", deploy_row.pk)
                return

            deploy = (
                Deploy.objects.select_related(
                    "service",
                    "service__plan",
                    "service__network",
                    "release_reference",
                    "release_reference__revision",
                    "release_reference__artifact",
                    "previous_deploy",
                    "previous_deploy__release_reference",
                    "previous_deploy__release_reference__revision",
                    "previous_deploy__release_reference__artifact",
                )
                .get(pk=deploy_row.pk)
            )
            service = deploy.service
            generation = int(getattr(service, "lifecycle_generation", 0) or 0)
            if generation != int(expected_lifecycle_generation):
                logger.warning(
                    "Skipping stale rollback attempt=%s expected_generation=%s actual_generation=%s",
                    deploy.pk,
                    expected_lifecycle_generation,
                    generation,
                )
                StateManager.transition_deploy_terminal_if_owned(
                    deploy.pk,
                    "cancelled",
                    task_id=str(task_id),
                    update_fields={
                        "stage": "cancelled",
                        "status_message": "Rollback was superseded by a newer service lifecycle operation.",
                        "rollback_status": RollbackStatusChoices.FAILED,
                    },
                )
                return

            current_deploy = get_authoritative_deploy(service)
            actual_previous_id = str(getattr(current_deploy, "pk", "") or "")
            if actual_previous_id != str(expected_previous_deploy_id or ""):
                logger.warning(
                    "Skipping stale rollback attempt=%s expected_active_deploy=%s actual_active_deploy=%s",
                    deploy.pk,
                    expected_previous_deploy_id,
                    actual_previous_id,
                )
                StateManager.transition_deploy_terminal_if_owned(
                    deploy.pk,
                    "cancelled",
                    task_id=str(task_id),
                    update_fields={
                        "stage": "cancelled",
                        "status_message": "Rollback was superseded by a newer service lifecycle operation.",
                        "rollback_status": RollbackStatusChoices.FAILED,
                    },
                )
                latest = Service.objects.select_for_update().filter(pk=service.pk).first()
                if (
                    latest is not None
                    and int(latest.lifecycle_generation or 0) == int(expected_lifecycle_generation)
                    and str(latest.task_id or "") == str(task_id)
                    and latest.status == "deploying"
                ):
                    StateManager.transition_service(
                        service.pk,
                        "running",
                        update_fields={
                            "desired_state": "running",
                            "task_id": None,
                            "deploy_started": None,
                        },
                    )
                return

            target_release = deploy.release_reference
            current_release = None
            if current_deploy is not None:
                current_release = (
                    Release.objects.filter(
                        service_id=service.pk,
                        revision_id=current_deploy.revision_id,
                        status="promoted",
                    )
                    .select_related("revision", "artifact")
                    .order_by("-promoted_at", "-created_at")
                    .first()
                )
            if (
                current_release is None
                and current_deploy is not None
                and getattr(current_deploy, "release_reference_id", None)
                and current_deploy.release_reference.status == "promoted"
            ):
                current_release = current_deploy.release_reference

            if (
                target_release is None
                or target_release.service_id != service.pk
                or target_release.artifact_id is None
                or target_release.revision_id is None
                or current_release is None
                or current_release.service_id != service.pk
            ):
                raise DeploymentError(
                    "Rollback requires a known-good immutable Release and artifact for this service.",
                    stage="rollback_validation",
                    code="ROLLBACK_RELEASE_UNAVAILABLE",
                    user_message="A previously deployed release is not available for rollback.",
                )

            if str(current_release.pk) == str(target_release.pk):
                raise DeploymentError(
                    "The requested rollback target is already the active Release.",
                    stage="rollback_validation",
                    code="ROLLBACK_TARGET_ALREADY_ACTIVE",
                    user_message="This release is already active.",
                )

            resolver = DjangoRuntimeSelectionResolver()
            target_service = copy(service)
            target_service.active_revision = target_release.revision
            target_deploy = deploy
            target_deploy.revision = target_release.revision
            target_deploy.release_reference = target_release
            target_selection = resolver.resolve(
                service=target_service,
                revision=target_release.revision,
                deployment=target_deploy,
                probe=True,
            )
            if target_selection.backend != RuntimeBackend.SWARM.value:
                raise DeploymentError(
                    "Immutable Release rollback is currently supported only by the native Swarm runtime.",
                    stage="rollback_validation",
                    code="ROLLBACK_RUNTIME_UNSUPPORTED",
                    user_message="Rollback is not supported by the selected runtime backend.",
                    details={"runtime_backend": target_selection.backend},
                )

            from deployments.celery.schedules import _native_reconciliation_plan

            target_plan = _native_reconciliation_plan(
                target_service,
                target_deploy,
                target_selection,
            )
            if target_plan is None:
                raise DeploymentError(
                    "The target Release could not be compiled into a native runtime plan.",
                    stage="rollback_planning",
                    code="ROLLBACK_TARGET_PLAN_UNAVAILABLE",
                    user_message="The previous release configuration is incomplete and cannot be restored safely.",
                )

            current_service = copy(service)
            current_service.active_revision = current_release.revision
            current_deploy.revision = current_release.revision
            current_deploy.release_reference = current_release
            current_selection = resolver.resolve(
                service=current_service,
                revision=current_release.revision,
                deployment=current_deploy,
                probe=True,
            )
            current_plan = _native_reconciliation_plan(
                current_service,
                current_deploy,
                current_selection,
            )
            if current_plan is None:
                raise DeploymentError(
                    "The currently active Release cannot be reconstructed for rollback recovery.",
                    stage="rollback_planning",
                    code="ROLLBACK_RECOVERY_PLAN_UNAVAILABLE",
                    user_message="The current release cannot be safely preserved while rolling back.",
                )

            target_plan = replace(target_plan, rollback_plan=current_plan)
            runtime = resolver.registry.resolve_adapter(target_selection)
            store = DjangoDeploymentLifecycleStore(
                int(deploy.pk),
                task_id=str(task_id),
                expected_active_revision_id=str(
                    getattr(service, "active_revision_id", None) or ""
                ),
                allow_active_revision_replacement=True,
            )

            def publish(event) -> None:
                from deployments.core.sink import DBAndChannelEventSink
                from deployments.core.types import DeploymentEvent

                DBAndChannelEventSink(deploy.pk)(
                    DeploymentEvent(
                        stage=event.stage,
                        message=event.message,
                        level=event.level,
                        progress=event.progress,
                        details=dict(event.details or {}),
                    )
                )

            context = DeploymentExecutionContext(
                deployment_id=str(deploy.pk),
                service_id=str(service.pk),
                revision_id=str(target_release.revision_id),
                worker_task_id=str(task_id),
                operation_key=f"rollback:{deploy.pk}:release:{target_release.pk}",
                runtime_selection=target_plan.runtime_selection,
                expected_lifecycle_generation=int(expected_lifecycle_generation),
                expected_previous_deploy_id=str(expected_previous_deploy_id),
                enforce_previous_deploy=True,
                owns_execution=lambda: StateManager.heartbeat_deploy(
                    deploy.pk,
                    task_id=str(task_id),
                    stage="rollback",
                ) and deployment_lock.assert_held(),
                cancellation_requested=lambda: bool(
                    Deploy.objects.filter(pk=deploy.pk)
                    .values_list("cancel_requested", flat=True)
                    .first()
                ),
                current_lifecycle_generation=lambda: Service.objects.filter(
                    pk=service.pk
                ).values_list("lifecycle_generation", flat=True).first(),
                publish=publish,
            )
            strategy = CallbackDeploymentStrategy(
                build_plan=lambda _context: target_plan,
            )
            result = DeploymentLifecycleExecutor(store).execute(
                context,
                strategy,
                runtime,
                readiness_timeout=float(
                    (target_release.health_policy or {}).get("timeout") or 180
                ),
            )

            if (
                result.retryable
                and result.error is not None
                and bool(getattr(result.error, "recoverable", False))
            ):
                # Leave rollback_status pending and retain the same Deploy +
                # Service owner token. Celery will retry this immutable target.
                raise result.error

            now = timezone.now()
            if result.success:
                latest_service = Service.objects.select_for_update().filter(pk=service.pk).first()
                if (
                    latest_service is None
                    or int(latest_service.lifecycle_generation or 0) != int(expected_lifecycle_generation)
                    or str(latest_service.active_revision_id or "") != str(target_release.revision_id)
                ):
                    Deploy.objects.filter(pk=deploy.pk).update(
                        reconciliation_required=True,
                        status_message="Rollback activation committed but its service projection requires reconciliation.",
                        updated_at=now,
                    )
                    logger.error(
                        "Rollback attempt=%s completed with a stale service projection; reconciliation required.",
                        deploy.pk,
                    )
                    return
                if latest_service.status != "running":
                    StateManager.transition_service(
                        service.pk,
                        "running",
                        update_fields={
                            "desired_state": "running",
                            "task_id": None,
                            "deploy_started": None,
                        },
                        allow_runtime_reconciliation=True,
                        expected_lifecycle_generation=expected_lifecycle_generation,
                    )
                Deploy.objects.filter(pk=deploy.pk).update(
                    rollback_status=RollbackStatusChoices.SUCCEEDED,
                    stage="rollback_completed",
                    operation="rollback_completed",
                    updated_at=now,
                )
                Deploy.objects.filter(pk=current_deploy.pk).update(
                    rollback_status=RollbackStatusChoices.SUCCEEDED,
                    updated_at=now,
                )
                logger.info(
                    "Rollback attempt=%s promoted release=%s revision=%s for service=%s",
                    deploy.pk,
                    target_release.pk,
                    target_release.revision_id,
                    service.pk,
                )
                return

            Deploy.objects.filter(pk=deploy.pk).update(
                rollback_status=RollbackStatusChoices.FAILED,
                stage="rollback_failed",
                operation="rollback_failed",
                reconciliation_required=bool(
                    result.rollback_failed or result.details.get("reconciliation_required")
                ),
                updated_at=now,
            )
            Deploy.objects.filter(pk=current_deploy.pk).update(
                rollback_status=RollbackStatusChoices.FAILED,
                updated_at=now,
            )

            # The executor attempts to restore the previous release if the
            # target release fails readiness. Verify the old runtime before
            # projecting the Service as RUNNING; unknown runtime state fails
            # closed and remains visible for reconciliation.
            restored = bool(result.rollback_performed and not result.rollback_failed)
            if not restored:
                try:
                    observed = runtime.inspect(current_plan.identity)
                    restored = str(observed.status.value).lower() == "ready"
                except Exception:
                    logger.exception(
                        "Could not verify runtime after rollback failure for service=%s",
                        service.pk,
                    )

            latest_service = Service.objects.filter(pk=service.pk).first()
            if latest_service is not None and latest_service.status == "deploying":
                StateManager.transition_service(
                    service.pk,
                    "running" if restored else "failed",
                    update_fields={
                        "desired_state": "running" if restored else latest_service.desired_state,
                        "task_id": None,
                        "deploy_started": None,
                    },
                )

            error = result.error or DeploymentError(
                "The runtime could not complete the requested rollback.",
                stage="rollback_failed",
                code="ROLLBACK_EXECUTION_FAILED",
                user_message="Rollback failed. The previous runtime was retained when possible.",
                details=dict(result.details or {}),
            )
            raise error


__all__ = ["ReleaseRollbackService"]
