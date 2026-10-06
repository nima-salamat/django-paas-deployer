from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from deploy.models import DeploymentStatusChoices
from deployments.core.state.manager import StateManager

from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from services.models import Service, ServiceNetworkAttachment
from services.signals import cleanup_service_resources, delete_service_row_after_cleanup
from .plan import ApplicationPlan, ServicePlan, ready_service_keys

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceDispatch:
    binding_id: int
    deploy_id: str
    instance_id: str
    service_key: str
    task_id: str
    platform: str = ""


class ApplicationStackExecutor:
    """Coordinates child Deploy executions without replacing the Deploy engine.

    The executor owns only application-level coordination: dependency ordering,
    parallel dispatch, cancellation propagation, timeout convergence, and
    application-level terminal state. Individual Deploy rows remain the source
    of truth for Docker/build/readiness execution.
    """

    def __init__(self, instance_id: str):
        self.instance_id = str(instance_id)

    def _load(self) -> tuple[ApplicationInstance, ApplicationPlan]:
        """Load only the immutable coordinator graph persisted at installation time."""
        instance = ApplicationInstance.objects.prefetch_related("services__deploy").get(pk=self.instance_id)
        snapshot = dict(instance.definition_snapshot or {})
        graph = dict(snapshot.get("_application_orchestration") or {})
        specs = list(graph.get("services") or [])
        if not specs:
            raise ValueError("Application installation is missing its immutable orchestration graph.")
        service_plans = [
            ServicePlan(
                key=str(spec["key"]),
                role=str(spec.get("role") or "app"),
                platform=str(spec.get("platform") or "docker"),
                plan_type=str(spec.get("plan_type") or "APP"),
                dependencies=tuple(str(dep) for dep in (spec.get("depends_on") or ())),
                required=bool(spec.get("required", True)),
            )
            for spec in specs
        ]
        plan = ApplicationPlan(
            id=str(instance.catalog_id),
            version=str(instance.definition_version),
            variant=str(instance.variant_id),
            services=tuple(service_plans),
        )
        plan.topological_order()
        plan.validate_dependency_semantics()
        binding_keys = {str(key) for key in instance.services.values_list("service_key", flat=True)}
        graph_keys = {service.key for service in plan.services}
        if binding_keys != graph_keys:
            raise ValueError("Application service bindings do not match the immutable application graph.")
        return instance, plan
    @staticmethod
    def _timeout_minutes() -> int:
        try:
            return max(1, int(getattr(settings, "CATALOG_APPLICATION_TIMEOUT_MINUTES", 60)))
        except (TypeError, ValueError):
            return 60

    def start(self, *, task_id: str | None = None) -> bool:
        """Claim application execution exactly once.

        A duplicate Celery delivery must not overwrite the owner task id or
        restart an already-running application coordinator.
        """
        now = timezone.now()
        deadline = now + timedelta(minutes=self._timeout_minutes())
        with transaction.atomic():
            instance = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
                return False
            if instance.status == ApplicationStatus.DEPLOYING:
                current_owner = str(instance.execution_task_id or "")
                requested_owner = str(task_id or "")
                if current_owner and requested_owner and current_owner != requested_owner:
                    return False
                return True
            instance.status = ApplicationStatus.DEPLOYING
            instance.stage = "dependency_resolution"
            instance.started_at = instance.started_at or now
            instance.execution_deadline = instance.execution_deadline or deadline
            if task_id:
                instance.execution_task_id = str(task_id)
            instance.save(update_fields=[
                "status", "stage", "started_at", "execution_deadline",
                "execution_task_id", "updated_at",
            ])
            return True

    def cancel(self, *, reason: str = "Application deployment cancelled.") -> None:
        with transaction.atomic():
            instance = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED}:
                return

            # Cancellation is intentionally idempotent even after the parent
            # has already converged to CANCELLED. A later delete/reconcile call
            # may still need to propagate cancellation to a child deployment
            # that was slow to stop.
            if instance.status != ApplicationStatus.CANCELLED:
                instance.cancel_requested = True
                instance.stage = "cancellation_requested"
                instance.error_code = "APPLICATION_DEPLOYMENT_CANCELLED"
                instance.error_message = reason
                instance.save(update_fields=[
                    "cancel_requested", "stage", "error_code", "error_message", "updated_at",
                ])
            elif not instance.cancel_requested:
                return

            rows = list(
                ApplicationInstanceService.objects.select_related("deploy")
                .select_for_update()
                .filter(instance_id=self.instance_id)
            )

        for binding in rows:
            deploy = binding.deploy
            if deploy.status in {
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
                DeploymentStatusChoices.ROLLING_BACK,
            }:
                deploy.cancel_requested = True
                deploy.status_message = reason[:500]
                deploy.error_message = ""
                deploy.save(
                    update_fields=[
                        "cancel_requested",
                        "status_message",
                        "error_message",
                        "updated_at",
                    ]
                )
                if deploy.status == DeploymentStatusChoices.PENDING:
                    try:
                        StateManager.transition_deploy_system_terminal(
                            deploy.pk,
                            DeploymentStatusChoices.CANCELLED,
                            update_fields={
                                "cancel_requested": True,
                                "stage": "cancelled",
                                "progress": 100,
                                "status_message": "Service was not started because the application was cancelled.",
                            },
                            event_payload={
                                "event_id": str(uuid.uuid4()),
                                "trace_id": str(deploy.pk),
                                "event_type": "deployment.cancelled.warning",
                                "stage": "cancelled",
                                "level": "warning",
                                "message": "Service was not started because the application was cancelled.",
                                "progress": 100,
                                "details": {"controlled_by": "application_executor"},
                            },
                        )
                    except Exception:
                        logger.exception("Unable to cancel pending child deploy %s", deploy.pk)

    def _cleanup_cancelled_children(self) -> bool:
        """Delete cancelled child resources through the normal Service boundary.

        The application row stays as durable cancellation history. The instance
        lock is held while child bindings/services and the private network are
        removed so concurrent reconciliation cannot run the same cleanup twice.
        """
        from .services import application_services_for_cleanup

        with transaction.atomic():
            locked = (
                ApplicationInstance.objects
                .select_for_update()
                # Keep the application row lock independent from the nullable network FK.
                # select_related("network") would emit a LEFT OUTER JOIN and PostgreSQL
                # rejects FOR UPDATE when the nullable side is joined.
                .get(pk=self.instance_id)
            )
            if locked.status != ApplicationStatus.CANCELLED or not locked.cancel_requested:
                return False

            bindings, service_rows, unexpected = application_services_for_cleanup(locked)
            if unexpected:
                names = ", ".join(str(service.name) for service in unexpected[:5])
                suffix = "..." if len(unexpected) > 5 else ""
                raise RuntimeError(
                    "Ready App private network still has services that are not owned "
                    f"by this installation: {names}{suffix}"
                )

            if any(
                binding.deploy.status in {
                    DeploymentStatusChoices.PENDING,
                    DeploymentStatusChoices.RUNNING,
                    DeploymentStatusChoices.ROLLING_BACK,
                }
                for binding in bindings
            ):
                return False

            network = locked.network
            locked.stage = "cancellation_cleanup"
            locked.save(update_fields=["stage", "updated_at"])

            # Preflight every child while all Service rows still exist. This
            # also recovers legacy installations whose binding was already lost.
            for service in service_rows:
                cleanup_service_resources(service)

            bindings_by_service = {str(binding.service_id): binding for binding in bindings}
            for service in service_rows:
                binding = bindings_by_service.get(str(service.pk))
                if binding is not None:
                    deploy = binding.deploy
                    if deploy.zip_file and deploy.zip_file.name:
                        deploy.zip_file.delete(save=False)
                    binding.delete()
                if Service.objects.filter(pk=service.pk).exists():
                    delete_service_row_after_cleanup(service)

            if network is not None:
                locked_network = type(network).objects.select_for_update().get(pk=network.pk)
                if (
                    Service.objects.filter(network_id=locked_network.pk).exists()
                    or ServiceNetworkAttachment.objects.filter(network_id=locked_network.pk).exists()
                ):
                    raise RuntimeError(
                        f"Ready App network '{locked_network.name}' is still referenced by another service."
                    )
                locked_network.delete()

            locked.stage = "cancelled"
            locked.network = None
            locked.save(update_fields=["stage", "network", "updated_at"])

        logger.info(
            "Cleaned cancelled Ready App installation %s; removed %d child services.",
            self.instance_id,
            len(service_rows),
        )
        return True

    def _fence_children_for_deletion(self) -> None:
        """Invalidate every child lifecycle operation before touching runtime resources."""
        from services.lifecycle import mark_deleted

        bindings = list(
            ApplicationInstanceService.objects
            .select_related("service", "deploy")
            .filter(instance_id=self.instance_id)
        )
        for binding in bindings:
            mark_deleted(binding.service_id)

        # The lifecycle fence prevents a stale worker from winning a later
        # activation after deletion has started.
        from services.signals import _cancel_active_deployments_for_service
        for binding in bindings:
            _cancel_active_deployments_for_service(binding.service)

    def _terminalize_cancelled_children_for_deletion(self) -> int:
        """Make cancellation authoritative after their runtime is gone."""
        bindings = list(
            ApplicationInstanceService.objects
            .select_related("deploy", "service")
            .filter(instance_id=self.instance_id)
        )
        terminalized = 0
        for binding in bindings:
            deploy = binding.deploy
            if deploy.status not in {
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
                DeploymentStatusChoices.ROLLING_BACK,
            }:
                continue
            if not deploy.cancel_requested:
                continue

            committed = StateManager.transition_deploy_system_terminal(
                deploy.pk,
                DeploymentStatusChoices.CANCELLED,
                update_fields={
                    "cancel_requested": True,
                    "stage": "cancelled",
                    "progress": 100,
                    "status_message": "Deployment cancelled because the owning Ready App is being deleted.",
                    "error_message": "",
                },
                event_payload={
                    "event_id": str(uuid.uuid4()),
                    "trace_id": str(deploy.pk),
                    "deployment_id": str(deploy.pk),
                    "service_id": str(deploy.service_id),
                    "revision_id": str(getattr(deploy, "revision_id", "") or ""),
                    "task_id": "ready-app-deletion",
                    "event_type": "deployment.cancelled.warning",
                    "stage": "cancelled",
                    "level": "warning",
                    "message": "Deployment cancelled because the owning Ready App is being deleted.",
                    "progress": 100,
                    "details": {"controlled_by": "ready_app_deletion"},
                },
            )
            if committed:
                terminalized += 1
        return terminalized

    def cleanup_terminal_application(self) -> bool:
        """Drive a Ready App deletion to completion, independent of child workers.

        Deletion is a durable application intent. Once deletion_pending is set,
        child lifecycle generations are fenced, active deployments are
        cancelled, runtime resources are removed, cancelled Deploy rows are
        terminalized, and only then is the database graph deleted.
        """
        from deploy.models import Deploy
        from .services import application_services_for_cleanup

        # Phase 1: persist deletion intent under a short application-row lock.
        with transaction.atomic():
            locked = (
                ApplicationInstance.objects
                .select_for_update()
                .filter(pk=self.instance_id)
                .first()
            )
            if locked is None:
                return True
            if locked.stage != "deletion_pending":
                return False

            if locked.status not in {ApplicationStatus.CANCELLED, ApplicationStatus.FAILED}:
                locked.cancel_requested = True
                locked.stage = "deletion_pending"
                locked.error_code = "APPLICATION_DELETION_PENDING"
                locked.error_message = (
                    "The Ready App is being deleted; active child deployments "
                    "are being cancelled and cleaned up."
                )
                locked.save(update_fields=[
                    "cancel_requested",
                    "stage",
                    "error_code",
                    "error_message",
                    "updated_at",
                ])

        # Phase 2: fence child lifecycle workers before runtime mutation.
        self._fence_children_for_deletion()

        # Phase 3: runtime cleanup without holding database locks.
        instance = ApplicationInstance.objects.get(pk=self.instance_id)
        bindings, service_rows, unexpected = application_services_for_cleanup(instance)
        if unexpected:
            names = ", ".join(str(service.name) for service in unexpected[:5])
            suffix = "..." if len(unexpected) > 5 else ""
            raise RuntimeError(
                "Ready App private network still has services that are not owned "
                f"by this installation: {names}{suffix}"
            )

        for service in service_rows:
            cleanup_service_resources(service)

        # Runtime resources are now gone. Cancellation is safe to commit even
        # when the original Celery worker disappeared or stopped responding.
        self._terminalize_cancelled_children_for_deletion()

        # Phase 4: verify quiescence and remove the complete DB graph.
        with transaction.atomic():
            locked = (
                ApplicationInstance.objects
                .select_for_update()
                .filter(pk=self.instance_id)
                .first()
            )
            if locked is None:
                return True

            bindings, service_rows, unexpected = application_services_for_cleanup(locked)
            if unexpected:
                names = ", ".join(str(service.name) for service in unexpected[:5])
                suffix = "..." if len(unexpected) > 5 else ""
                raise RuntimeError(
                    "Ready App private network still has services that are not owned "
                    f"by this installation: {names}{suffix}"
                )

            active = [
                binding for binding in bindings
                if binding.deploy.status in {
                    DeploymentStatusChoices.PENDING,
                    DeploymentStatusChoices.RUNNING,
                    DeploymentStatusChoices.ROLLING_BACK,
                }
            ]
            if active:
                locked.stage = "deletion_pending"
                locked.error_code = "APPLICATION_DELETION_PENDING"
                locked.error_message = f"{len(active)} child deployment(s) are still converging."
                locked.save(update_fields=[
                    "stage", "error_code", "error_message", "updated_at",
                ])
                return False

            network = locked.network
            bindings_by_service = {
                str(binding.service_id): binding for binding in bindings
            }

            for service in service_rows:
                for deploy in Deploy.objects.filter(service_id=service.pk).only("zip_file"):
                    if deploy.zip_file and deploy.zip_file.name:
                        deploy.zip_file.delete(save=False)

                binding = bindings_by_service.get(str(service.pk))
                if binding is not None:
                    binding.delete()
                if Service.objects.filter(pk=service.pk).exists():
                    delete_service_row_after_cleanup(service)

            if network is not None:
                locked_network = type(network).objects.select_for_update().get(pk=network.pk)
                if (
                    Service.objects.filter(network_id=locked_network.pk).exists()
                    or ServiceNetworkAttachment.objects.filter(network_id=locked_network.pk).exists()
                ):
                    raise RuntimeError(
                        f"Ready App network '{locked_network.name}' is still referenced after "
                        "all owned child services were deleted."
                    )
                locked_network.delete()

            locked.delete()

        logger.info(
            "Deleted Ready App installation %s; removed %d child services.",
            self.instance_id,
            len(service_rows),
        )
        return True

    def _dependency_map(self, plan: ApplicationPlan) -> dict[str, set[str]]:
        return {svc.key: set(svc.dependencies) for svc in plan.services}

    def _reconcile_terminal(self, instance: ApplicationInstance, plan: ApplicationPlan) -> bool:
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return True
            bindings = list(
                ApplicationInstanceService.objects.select_related("deploy").filter(instance_id=self.instance_id)
            )
            required = {svc.key: svc.required for svc in plan.services}
            status_by_key = {b.service_key: str(b.deploy.status) for b in bindings}

            for binding in bindings:
                if binding.deploy.status != DeploymentStatusChoices.PENDING:
                    continue
                spec = plan.service(binding.service_key)
                if any(
                    status_by_key.get(dep) in {
                        DeploymentStatusChoices.FAILED,
                        DeploymentStatusChoices.ROLLED_BACK,
                        DeploymentStatusChoices.CANCELLED,
                    }
                    for dep in spec.dependencies
                ):
                    StateManager.transition_deploy_system_terminal(
                        binding.deploy.pk,
                        DeploymentStatusChoices.CANCELLED,
                        update_fields={
                            "cancel_requested": True,
                            "stage": "cancelled",
                            "progress": 100,
                            "status_message": "Service was not started because a dependency became unavailable.",
                        },
                        event_payload={
                            "event_id": str(uuid.uuid4()),
                            "trace_id": str(binding.deploy.pk),
                            "event_type": "deployment.cancelled.warning",
                            "stage": "cancelled",
                            "level": "warning",
                            "message": "Service was not started because a dependency became unavailable.",
                            "progress": 100,
                            "details": {"controlled_by": "application_executor", "dependency_blocked": True},
                        },
                    )
                    status_by_key[binding.service_key] = DeploymentStatusChoices.CANCELLED

            failed = [
                b for b in bindings
                if required.get(b.service_key, True)
                and b.deploy.status in {
                    DeploymentStatusChoices.FAILED,
                    DeploymentStatusChoices.ROLLED_BACK,
                    DeploymentStatusChoices.CANCELLED,
                }
            ]
            if locked.cancel_requested:
                active = [
                    b for b in bindings
                    if b.deploy.status in {
                        DeploymentStatusChoices.PENDING,
                        DeploymentStatusChoices.RUNNING,
                        DeploymentStatusChoices.ROLLING_BACK,
                    }
                ]
                if not active:
                    locked.status = ApplicationStatus.CANCELLED
                    locked.stage = "cancelled"
                    locked.error_code = locked.error_code or "APPLICATION_DEPLOYMENT_CANCELLED"
                    locked.error_message = locked.error_message or "Application deployment cancelled."
                    locked.deployed_at = None
                    locked.save(update_fields=["status", "stage", "error_code", "error_message", "deployed_at", "updated_at"])
                    return True
                return False
            if failed:
                first = failed[0]
                message = first.deploy.error_message or first.deploy.status_message or "Service deployment did not complete."
                locked.status = ApplicationStatus.FAILED
                locked.stage = "service_failed"
                locked.error_code = "APPLICATION_SERVICE_DEPLOYMENT_FAILED"
                locked.error_message = f"{first.service_key}: {message}"
                locked.save(update_fields=["status", "stage", "error_code", "error_message", "updated_at"])
                for binding in bindings:
                    if binding.deploy.status == DeploymentStatusChoices.PENDING:
                        StateManager.transition_deploy_system_terminal(
                            binding.deploy.pk,
                            DeploymentStatusChoices.CANCELLED,
                            update_fields={
                                "cancel_requested": True,
                                "stage": "cancelled",
                                "progress": 100,
                                "status_message": (
                                    f"Service was not started because required application service "
                                    f"'{first.service_key}' failed."
                                ),
                                "error_message": "",
                            },
                            event_payload={
                                "event_id": str(uuid.uuid4()),
                                "trace_id": str(binding.deploy.pk),
                                "event_type": "deployment.cancelled.warning",
                                "stage": "cancelled",
                                "level": "warning",
                                "message": (
                                    f"Service was not started because required application service "
                                    f"'{first.service_key}' failed."
                                ),
                                "progress": 100,
                                "details": {"controlled_by": "application_executor", "dependency_failed": True},
                            },
                        )
                    elif binding.deploy.status in {
                        DeploymentStatusChoices.RUNNING,
                        DeploymentStatusChoices.ROLLING_BACK,
                    }:
                        binding.deploy.cancel_requested = True
                        binding.deploy.status_message = (
                            f"Deployment stopped because required application service "
                            f"'{first.service_key}' failed."
                        )
                        binding.deploy.error_message = ""
                        binding.deploy.save(
                            update_fields=[
                                "cancel_requested",
                                "status_message",
                                "error_message",
                                "updated_at",
                            ]
                        )
                return True
            required_bindings = [b for b in bindings if required.get(b.service_key, True)]
            all_terminal = all(
                b.deploy.status in {
                    DeploymentStatusChoices.SUCCEEDED,
                    DeploymentStatusChoices.FAILED,
                    DeploymentStatusChoices.ROLLED_BACK,
                    DeploymentStatusChoices.CANCELLED,
                }
                for b in bindings
            )
            if required_bindings and all_terminal and all(
                b.deploy.status == DeploymentStatusChoices.SUCCEEDED for b in required_bindings
            ):
                locked.status = ApplicationStatus.RUNNING
                locked.stage = "application_ready"
                locked.error_code = ""
                locked.error_message = ""
                locked.deployed_at = timezone.now()
                locked.save(update_fields=["status", "stage", "error_code", "error_message", "deployed_at", "updated_at"])
                return True
            return False

    def supervise_runtime(self) -> dict[str, object]:
        """Check a RUNNING Ready App's persisted application-level invariants.

        This is deliberately separate from Docker/runtime execution. The
        deployment monitor owns runtime repair; this supervisor owns the parent
        application's durable state and records when a running installation is
        temporarily degraded or structurally inconsistent.
        """
        current = ApplicationInstance.objects.filter(pk=self.instance_id).first()
        if current is None:
            return {"status": "missing"}

        # A live installation can legitimately pass through deletion_pending
        # while its resources are being removed. Do not report that cleanup
        # transition as runtime corruption.
        if (
            current.status != ApplicationStatus.RUNNING
            or current.stage == "deletion_pending"
        ):
            return {"status": "skipped", "application_status": str(current.status)}

        try:
            instance, plan = self._load()
        except ApplicationInstance.DoesNotExist:
            return {"status": "missing"}
        except Exception as exc:
            message = (
                "Ready App coordinator state is inconsistent and could not be "
                f"validated safely: {str(exc)[:450]}"
            )
            with transaction.atomic():
                locked = (
                    ApplicationInstance.objects
                    .select_for_update()
                    .filter(pk=self.instance_id)
                    .first()
                )
                if locked and locked.status == ApplicationStatus.RUNNING and locked.stage != "deletion_pending":
                    locked.status = ApplicationStatus.FAILED
                    locked.stage = "state_corrupted"
                    locked.error_code = "APPLICATION_STATE_CORRUPTED"
                    locked.error_message = message
                    locked.save(update_fields=[
                        "status", "stage", "error_code", "error_message", "updated_at",
                    ])
            logger.error("Ready App %s coordinator state is corrupted: %s", self.instance_id, exc)
            return {"status": "corrupted", "message": message}

        bindings = list(
            ApplicationInstanceService.objects
            .select_related("deploy", "service")
            .filter(instance_id=self.instance_id)
        )
        expected = {spec.key: spec for spec in plan.services}
        actual = {binding.service_key: binding for binding in bindings}

        structural_errors: list[str] = []
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            structural_errors.append("missing child service bindings: " + ", ".join(missing))
        if extra:
            structural_errors.append("unexpected child service bindings: " + ", ".join(extra))

        if not instance.network_id:
            structural_errors.append("application private network is missing")
        else:
            from services.models import PrivateNetwork
            if not PrivateNetwork.objects.filter(pk=instance.network_id).exists():
                structural_errors.append("application private network record is missing")

        for key, binding in actual.items():
            if key not in expected:
                continue
            if binding.service.network_id != instance.network_id:
                structural_errors.append(
                    f"child service '{key}' is attached to a different private network"
                )

        if structural_errors:
            message = (
                "Ready App coordinator state is structurally inconsistent: "
                + "; ".join(structural_errors[:5])
            )
            with transaction.atomic():
                locked = (
                    ApplicationInstance.objects
                    .select_for_update()
                    .filter(pk=self.instance_id)
                    .first()
                )
                if locked and locked.status == ApplicationStatus.RUNNING and locked.stage != "deletion_pending":
                    locked.status = ApplicationStatus.FAILED
                    locked.stage = "state_corrupted"
                    locked.error_code = "APPLICATION_STATE_CORRUPTED"
                    locked.error_message = message
                    locked.save(update_fields=[
                        "status", "stage", "error_code", "error_message", "updated_at",
                    ])
            logger.error(
                "Ready App %s coordinator invariants failed: %s",
                self.instance_id,
                message,
            )
            return {"status": "corrupted", "message": message}

        runtime_issues: list[str] = []
        for spec in plan.services:
            binding = actual[spec.key]
            deploy_status = str(binding.deploy.status or "").lower()
            service_status = str(binding.service.status or "").lower()
            desired_state = str(binding.service.desired_state or "").lower()

            terminal = deploy_status in {
                DeploymentStatusChoices.SUCCEEDED,
                DeploymentStatusChoices.FAILED,
                DeploymentStatusChoices.ROLLED_BACK,
                DeploymentStatusChoices.CANCELLED,
            }
            if not terminal:
                runtime_issues.append(
                    f"{spec.key}: child deployment is still {deploy_status or 'unknown'}"
                )
            elif spec.required and deploy_status != DeploymentStatusChoices.SUCCEEDED:
                runtime_issues.append(
                    f"{spec.key}: required child deployment is {deploy_status}"
                )

            if desired_state != "running":
                runtime_issues.append(
                    f"{spec.key}: desired state is {desired_state or 'unset'}"
                )

            if deploy_status == DeploymentStatusChoices.SUCCEEDED and service_status not in {
                "running",
                "succeeded",
            }:
                runtime_issues.append(
                    f"{spec.key}: deployment succeeded but service state is {service_status or 'unknown'}"
                )

        with transaction.atomic():
            locked = (
                ApplicationInstance.objects
                .select_for_update()
                .filter(pk=self.instance_id)
                .first()
            )
            if not locked or locked.status != ApplicationStatus.RUNNING or locked.stage == "deletion_pending":
                return {"status": "skipped"}

            if runtime_issues:
                locked.stage = "runtime_reconciling"
                locked.error_code = "APPLICATION_RUNTIME_DEGRADED"
                locked.error_message = (
                    "Ready App runtime is temporarily degraded; the deployment "
                    "monitor is reconciling child services. "
                    + "; ".join(runtime_issues[:5])
                )
                locked.save(update_fields=[
                    "stage", "error_code", "error_message", "updated_at",
                ])
                return {
                    "status": "degraded",
                    "issues": runtime_issues,
                }

            locked.stage = "application_ready"
            locked.error_code = ""
            locked.error_message = ""
            locked.deployed_at = locked.deployed_at or timezone.now()
            locked.save(update_fields=[
                "stage", "error_code", "error_message", "deployed_at", "updated_at",
            ])
            return {"status": "healthy"}
    
    def reconcile(self) -> list[ServiceDispatch]:
        # Cancellation cleanup removes ApplicationInstanceService bindings.
        # Handle terminal cancellation before _load(), which requires the
        # complete immutable binding graph to still exist.
        current = ApplicationInstance.objects.filter(pk=self.instance_id).first()
        if current is None:
            return []
        if current.status == ApplicationStatus.CANCELLED and current.cancel_requested:
            self._cleanup_cancelled_children()
            return []
        if current.status in {
            ApplicationStatus.FAILED,
            ApplicationStatus.RUNNING,
        }:
            return []

        instance, plan = self._load()
        bindings = list(
            ApplicationInstanceService.objects.select_related("deploy")
            .filter(instance_id=self.instance_id)
        )
        by_key = {b.service_key: b for b in bindings}
        if set(by_key) != {s.key for s in plan.services}:
            raise ValueError("Application instance service bindings do not match its application plan.")

        now = timezone.now()
        should_cancel = False
        cancel_reason = "Application deployment cancelled."
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return []
            if locked.execution_deadline and now >= locked.execution_deadline:
                locked.cancel_requested = True
                locked.stage = "timeout_requested"
                locked.error_code = "APPLICATION_DEPLOYMENT_TIMEOUT"
                locked.error_message = "The application deployment exceeded its maximum allowed time."
                locked.save(update_fields=[
                    "cancel_requested", "stage", "error_code", "error_message", "updated_at",
                ])
            should_cancel = bool(locked.cancel_requested)
            cancel_reason = locked.error_message or cancel_reason

        # Re-read the authoritative locked state above. Do not rely on the
        # earlier unlocked instance snapshot; a concurrent API cancellation
        # must stop scheduling new child services in this reconciliation.
        if should_cancel:
            self.cancel(reason=cancel_reason)
            latest, _ = self._load()
            self._reconcile_terminal(latest, plan)
            return []

        if self._reconcile_terminal(instance, plan):
            latest = ApplicationInstance.objects.get(pk=self.instance_id)
            if latest.status == ApplicationStatus.CANCELLED and latest.cancel_requested:
                self._cleanup_cancelled_children()
            return []

        dispatches: list[ServiceDispatch] = []
        bindings = list(
            ApplicationInstanceService.objects.select_related("deploy")
            .filter(instance_id=self.instance_id)
        )
        status_by_key = {b.service_key: b.deploy.status for b in bindings}
        claimed = {b.service_key for b in bindings if b.dispatched_at is not None}
        ready_keys = set(ready_service_keys(plan, status_by_key, claimed))
        stale_before = now - timedelta(seconds=300)

        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return []
            if locked.cancel_requested or (locked.execution_deadline and now >= locked.execution_deadline):
                return []
            for binding in ApplicationInstanceService.objects.select_for_update().select_related("deploy").filter(instance_id=self.instance_id):
                if binding.dispatched_at is not None and binding.dispatched_at < stale_before and binding.deploy.status == DeploymentStatusChoices.PENDING:
                    binding.dispatched_at = None
                    binding.save(update_fields=["dispatched_at"])
                if binding.dispatched_at is not None:
                    continue
                deploy = binding.deploy
                if deploy.status != DeploymentStatusChoices.PENDING:
                    continue
                if binding.service_key not in ready_keys:
                    continue
                token = str(uuid.uuid4())
                binding.dispatch_task_id = token
                binding.dispatched_at = now
                binding.save(update_fields=["dispatch_task_id", "dispatched_at"])
                dispatches.append(ServiceDispatch(
                    binding_id=binding.pk,
                    deploy_id=binding.deploy_id,
                    instance_id=self.instance_id,
                    service_key=binding.service_key,
                    task_id=token,
                    platform=str(
                        getattr(getattr(deploy.service, "plan", None), "platform", "")
                        or ""
                    ).strip().lower(),
                ))
            if dispatches:
                locked.stage = "dispatching_services"
                locked.save(update_fields=["stage", "updated_at"])

        return dispatches


__all__ = ["ApplicationStackExecutor", "ServiceDispatch"]
