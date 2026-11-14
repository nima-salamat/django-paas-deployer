import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.global_settings.config import PlanTypeChoices, SERVICE_STATUS_CHOICES
from deploy.models import DeploymentStatusChoices
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication
from core.throttling import GlobalIPRateThrottle, GlobalUserRateThrottle, UserScopedRateThrottle
from .catalog import ApplicationCatalog, CatalogValidationError
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from .serializers import (
    ApplicationInstanceSerializer,
    catalog_listing,
    is_public_definition,
    public_catalog_definition,
    public_resolution_payload,
)
from .services import (
    ApplicationNameConflict,
    create_application_installation,
    prepare_application_resolution,
    resource_summary_for_resolved,
    safe_slug,
)
from services.models import Service
from services.lifecycle import bump_lifecycle

logger = logging.getLogger(__name__)
from services.signals import cleanup_service_resources, delete_service_row_after_cleanup
from .tasks import (
    start_application_installation,
    cancel_application_installation,
    delete_application_installation,
    start_application_runtime,
    stop_application_runtime,
)


def _queue_ready_app_deletion(instance_id: str) -> bool:
    """Request deletion once and let durable reconciliation own subsequent retries."""
    from django.db import transaction
    from django.utils import timezone

    # Claim deletion intent under the application row lock. Only the
    # transaction that changes the row into deletion_pending is allowed to
    # enqueue the first asynchronous deletion attempt.
    with transaction.atomic():
        instance = (
            ApplicationInstance.objects
            .select_for_update()
            .filter(pk=instance_id)
            .first()
        )
        if instance is None:
            return True

        already_pending = (
            instance.stage == "deletion_pending"
            and instance.error_code == "APPLICATION_DELETION_PENDING"
        )
        if not already_pending:
            instance.stage = "deletion_pending"
            instance.error_code = "APPLICATION_DELETION_PENDING"
            instance.runtime_operation = ""
            instance.runtime_operation_generation = int(instance.runtime_operation_generation or 0) + 1
            instance.save(update_fields=[
                "stage", "error_code", "runtime_operation",
                "runtime_operation_generation", "updated_at",
            ])

    # Always make one bounded synchronous attempt. If the service is still
    # active, cleanup_terminal_application requests cancellation and returns
    # False; the periodic reconciliation task will continue from there.
    try:
        from .executor import ApplicationStackExecutor

        deleted = ApplicationStackExecutor(str(instance_id)).cleanup_terminal_application()
        if deleted:
            return True
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception(
            "Immediate Ready App deletion convergence failed for %s; "
            "durable reconciliation remains responsible for retrying.",
            instance_id,
        )

    # Only the first transaction that claimed deletion intent may enqueue the
    # durable task. Later concurrent DELETE requests rely on reconciliation.
    if already_pending:
        return False

    try:
        delete_application_installation.delay(str(instance_id))
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("Unable to queue Ready App deletion %s", instance_id)
    return False



class CatalogPermissionMixin:
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [GlobalIPRateThrottle, GlobalUserRateThrottle, UserScopedRateThrottle]
    throttle_user_rate = "10/min"
    throttle_scope = "catalog.mutation"

    def get_throttles(self):
        if self.request.method in {"POST", "DELETE"}:
            return [throttle() for throttle in self.throttle_classes]
        return [GlobalIPRateThrottle(), GlobalUserRateThrottle()]


class CatalogListAPIView(CatalogPermissionMixin, APIView):
    def get(self, request):
        return Response(catalog_listing())


class CatalogDetailAPIView(CatalogPermissionMixin, APIView):
    def get(self, request, catalog_id):
        try:
            definition = ApplicationCatalog.get(catalog_id)
        except KeyError:
            return Response({"error": "Catalog application not found."}, status=404)
        if not is_public_definition(definition):
            return Response({"error": "Catalog application not found."}, status=404)
        return Response(public_catalog_definition(definition))


class CatalogResolveAPIView(CatalogPermissionMixin, APIView):
    def post(self, request, catalog_id):
        try:
            definition = ApplicationCatalog.get(catalog_id)
            if not is_public_definition(definition):
                return Response({"error": "Catalog application not found."}, status=404)

            name = str(request.data.get("name") or "").strip()
            plan_id = request.data.get("plan_id")
            service_plan_ids = request.data.get("service_plan_ids")
            variant = str(request.data.get("variant") or "").strip()
            config = request.data.get("config") or {}

            if not name or not (plan_id or service_plan_ids) or not variant:
                raise CatalogValidationError(
                    "name, variant, and a plan selection for every service are required."
                )
            if not isinstance(config, dict):
                raise CatalogValidationError("config must be an object.")

            resolved = prepare_application_resolution(
                definition,
                variant,
                name,
                config,
                public=True,
            )

            from plans.models import Plan
            plan = Plan.objects.filter(pk=plan_id).first() if plan_id else None
            if plan_id and (
                not plan
                or str(plan.platform).strip().lower() != "docker"
                or str(plan.plan_type) not in {
                    str(PlanTypeChoices.APP),
                    str(PlanTypeChoices.READY),
                }
            ):
                raise CatalogValidationError("The fallback plan must be a Docker application/ready-made plan.")

            resource_summary = resource_summary_for_resolved(
                resolved,
                plan,
                service_plan_ids=service_plan_ids,
            )
            return Response(public_resolution_payload(definition, resolved, resource_summary))
        except (KeyError, CatalogValidationError) as exc:
            return Response({"error": str(exc)}, status=400)


class ApplicationInstanceListCreateAPIView(CatalogPermissionMixin, APIView):
    def get(self, request):
        rows = ApplicationInstance.objects.filter(user=request.user).prefetch_related("services__service", "services__deploy")
        return Response(ApplicationInstanceSerializer(rows, many=True).data)

    def post(self, request):
        try:
            instance = create_application_installation(
                request.user,
                request.data,
                require_public=True,
            )
        except ApplicationNameConflict as exc:
            existing_id = exc.existing_installation_id
            if not existing_id:
                try:
                    requested_name = str(request.data.get("name") or "")
                    existing_id = (
                        ApplicationInstance.objects
                        .filter(user=request.user, slug=safe_slug(requested_name))
                        .values_list("pk", flat=True)
                        .first()
                    )
                except Exception:
                    existing_id = None
            return Response(
                {
                    "error": str(exc),
                    "code": "application_name_conflict",
                    **({"existing_installation_id": str(existing_id)} if existing_id else {}),
                },
                status=status.HTTP_409_CONFLICT,
            )
        except (CatalogValidationError, ValueError) as exc:
            return Response({"error": str(exc)}, status=400)
        try:
            start_application_installation.delay(str(instance.pk))
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Unable to queue application installation %s", instance.pk)
            # Keep the installation PENDING rather than terminal FAILED so the
            # periodic coordinator can requeue it after a transient broker
            # outage. Child Deploy rows have not started yet.
            ApplicationInstance.objects.filter(pk=instance.pk, status=ApplicationStatus.PENDING).update(
                stage="queue_failed",
                error_code="APPLICATION_TASK_QUEUE_FAILED",
                error_message="The deployment worker could not be queued. The installation will be retried when the worker is available.",
                execution_task_id="",
            )
            return Response(
                {
                    "error": "The deployment worker could not be queued.",
                    "code": "APPLICATION_TASK_QUEUE_FAILED",
                    "detail": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ApplicationInstanceSerializer(instance).data, status=status.HTTP_202_ACCEPTED)


class ApplicationInstanceDetailAPIView(CatalogPermissionMixin, APIView):
    def get(self, request, pk):
        instance = get_object_or_404(
            ApplicationInstance.objects.filter(user=request.user).prefetch_related("services__service", "services__deploy"),
            pk=pk,
        )
        return Response(ApplicationInstanceSerializer(instance).data)

    def delete(self, request, pk):
        instance = get_object_or_404(
            ApplicationInstance.objects.filter(user=request.user),
            pk=pk,
        )

        # Deletion is a durable intent and is valid for every application
        # lifecycle state, including PENDING/DEPLOYING. The coordinator first
        # fences/cancels child work and only then removes runtime and DB state.
        deleted_now = _queue_ready_app_deletion(str(instance.pk))
        if deleted_now:
            return Response(status=status.HTTP_204_NO_CONTENT)

        instance.refresh_from_db()
        return Response(
            {
                "error": "Cleanup is still in progress.",
                "code": "application_cleanup_pending",
                "detail": (
                    "The application has been marked for deletion. PassDeployer "
                    "is cancelling active work and retrying runtime cleanup automatically."
                ),
                "status": instance.status,
                "stage": instance.stage,
            },
            status=status.HTTP_202_ACCEPTED,
        )

class ApplicationInstanceStartAPIView(CatalogPermissionMixin, APIView):
    """Start a fully stopped Ready App through the persisted dependency DAG."""

    def post(self, request, pk):
        try:
            with transaction.atomic():
                instance = (
                    ApplicationInstance.objects.select_for_update()
                    .filter(user=request.user)
                    .filter(pk=pk)
                    .first()
                )
                if instance is None:
                    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
                if instance.stage == "deletion_pending":
                    return Response(
                        {"detail": "This application is being deleted.", "code": "application_deletion_pending"},
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.status == ApplicationStatus.DEPLOYING or instance.status == ApplicationStatus.STOPPING:
                    return Response(
                        {"detail": "An application lifecycle operation is already in progress.", "status": instance.status},
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.status == ApplicationStatus.DEGRADED:
                    return Response(
                        {
                            "detail": "This application has a degraded runtime. Use Stop All first to confirm every service is stopped, then run Start All.",
                            "code": "application_stop_before_restart",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.status not in {ApplicationStatus.STOPPED, ApplicationStatus.RUNNING}:
                    return Response(
                        {"detail": "This installation is not in a restartable state. Reinstall it or inspect the failed installation first."},
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.runtime_operation:
                    return Response(
                        {"detail": "An application lifecycle operation is already in progress."},
                        status=status.HTTP_409_CONFLICT,
                    )

                from .executor import ApplicationStackExecutor
                try:
                    _loaded, plan = ApplicationStackExecutor(str(instance.pk))._load()
                except Exception as exc:
                    return Response(
                        {"detail": f"The saved application dependency graph is invalid: {exc}"},
                        status=status.HTTP_409_CONFLICT,
                    )

                bindings = {
                    row.service_key: row
                    for row in (
                        ApplicationInstanceService.objects
                        .select_for_update()
                        .select_related("service", "deploy")
                        .filter(instance_id=instance.pk)
                    )
                }
                if set(bindings) != {spec.key for spec in plan.services}:
                    return Response(
                        {"detail": "The application's managed services do not match its saved dependency graph."},
                        status=status.HTTP_409_CONFLICT,
                    )

                to_start = []
                for key in plan.topological_order():
                    binding = bindings[key]
                    service = binding.service
                    service_status = str(service.status or "").lower()
                    desired_state = str(service.desired_state or "").lower()
                    deploy_status = str(binding.deploy.status or "").lower()

                    if (
                        service_status == str(SERVICE_STATUS_CHOICES.RUNNING).lower()
                        and desired_state == "running"
                        and deploy_status == str(DeploymentStatusChoices.SUCCEEDED).lower()
                    ):
                        continue

                    if service_status != str(SERVICE_STATUS_CHOICES.STOPPED).lower():
                        return Response(
                            {
                                "detail": (
                                    f"Cannot start all services safely: '{key}' is {service_status or 'unknown'}. "
                                    "Use Stop All first so every child runtime is confirmed stopped."
                                ),
                                "service_key": key,
                                "service_status": service_status,
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    if deploy_status not in {
                        str(DeploymentStatusChoices.SUCCEEDED).lower(),
                        str(DeploymentStatusChoices.FAILED).lower(),
                        str(DeploymentStatusChoices.ROLLED_BACK).lower(),
                        str(DeploymentStatusChoices.CANCELLED).lower(),
                    }:
                        return Response(
                            {
                                "detail": f"Cannot start '{key}' because its deployment is still {deploy_status or 'unknown'}.",
                                "service_key": key,
                                "deploy_status": deploy_status,
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    to_start.append(binding)

                if not to_start:
                    if instance.status != ApplicationStatus.RUNNING:
                        instance.status = ApplicationStatus.RUNNING
                        instance.stage = "application_ready"
                        instance.error_code = ""
                        instance.error_message = ""
                        instance.runtime_operation = ""
                        instance.save(update_fields=[
                            "status", "stage", "error_code", "error_message",
                            "runtime_operation", "updated_at",
                        ])
                    return Response(
                        ApplicationInstanceSerializer(instance).data,
                        status=status.HTTP_200_OK,
                    )

                now = timezone.now()
                execution_deadline = now + timedelta(
                    minutes=ApplicationStackExecutor._timeout_minutes()
                )
                for binding in to_start:
                    service = binding.service
                    generation = bump_lifecycle(service.pk, desired_state="running")
                    service.status = SERVICE_STATUS_CHOICES.QUEUED
                    service.desired_state = "running"
                    service.lifecycle_generation = generation
                    service.task_id = ""
                    service.deploy_started = now
                    service.save(update_fields=[
                        "status", "desired_state", "lifecycle_generation",
                        "task_id", "deploy_started",
                    ])

                    deploy = binding.deploy
                    deploy.status = DeploymentStatusChoices.PENDING
                    deploy.stage = "queued"
                    deploy.progress = 0
                    deploy.status_message = "Application Start All queued this service."
                    deploy.error_message = ""
                    deploy.cancel_requested = False
                    deploy.execution_task_id = ""
                    deploy.expected_lifecycle_generation = generation
                    deploy.expected_active_revision_id = str(service.active_revision_id or "")
                    deploy.worker_recovery_attempts = 0
                    deploy.save(update_fields=[
                        "status", "stage", "progress", "status_message",
                        "error_message", "cancel_requested", "execution_task_id",
                        "expected_lifecycle_generation", "expected_active_revision_id",
                        "worker_recovery_attempts", "updated_at",
                    ])
                    binding.dispatched_at = None
                    binding.dispatch_task_id = ""
                    binding.save(update_fields=["dispatched_at", "dispatch_task_id"])

                instance.status = ApplicationStatus.DEPLOYING
                instance.stage = "starting_services"
                instance.runtime_operation = "start"
                instance.runtime_operation_generation = int(instance.runtime_operation_generation or 0) + 1
                instance.cancel_requested = False
                instance.started_at = now
                instance.execution_deadline = execution_deadline
                instance.error_code = ""
                instance.error_message = ""
                instance.save(update_fields=[
                    "status", "stage", "runtime_operation",
                    "runtime_operation_generation", "cancel_requested",
                    "started_at", "execution_deadline",
                    "error_code", "error_message", "updated_at",
                ])
                operation_generation = int(instance.runtime_operation_generation)

            try:
                start_application_runtime.delay(str(instance.pk), operation_generation)
            except Exception:
                # The operation intent is durable; the periodic coordinator
                # reconciler will resume it when the broker is available.
                logger.exception("Unable to enqueue Start All for application %s", instance.pk)

            instance.refresh_from_db()
            return Response(
                ApplicationInstanceSerializer(instance).data,
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception:
            logger.exception("Ready App Start All failed for %s", pk)
            return Response(
                {"detail": "The application could not be queued for startup."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class ApplicationInstanceStopAPIView(CatalogPermissionMixin, APIView):
    """Stop child services one by one in reverse dependency order."""

    def post(self, request, pk):
        try:
            with transaction.atomic():
                instance = (
                    ApplicationInstance.objects.select_for_update()
                    .filter(user=request.user)
                    .filter(pk=pk)
                    .first()
                )
                if instance is None:
                    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
                if instance.stage == "deletion_pending":
                    return Response(
                        {"detail": "This application is being deleted.", "code": "application_deletion_pending"},
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.status == ApplicationStatus.STOPPED:
                    return Response(
                        ApplicationInstanceSerializer(instance).data,
                        status=status.HTTP_200_OK,
                    )
                if instance.status == ApplicationStatus.STOPPING and instance.runtime_operation == "stop":
                    return Response(
                        ApplicationInstanceSerializer(instance).data,
                        status=status.HTTP_202_ACCEPTED,
                    )
                if instance.status != ApplicationStatus.RUNNING and instance.status != ApplicationStatus.DEGRADED:
                    return Response(
                        {"detail": "Stop All is available only for running or degraded applications.", "status": instance.status},
                        status=status.HTTP_409_CONFLICT,
                    )
                if instance.runtime_operation:
                    return Response(
                        {"detail": "Another application lifecycle operation is already in progress."},
                        status=status.HTTP_409_CONFLICT,
                    )

                bindings = list(
                    ApplicationInstanceService.objects
                    .select_for_update()
                    .select_related("service")
                    .filter(instance_id=instance.pk)
                )
                for binding in bindings:
                    service_status = str(binding.service.status or "").lower()
                    if service_status in {
                        str(SERVICE_STATUS_CHOICES.QUEUED).lower(),
                        str(SERVICE_STATUS_CHOICES.DEPLOYING).lower(),
                    }:
                        return Response(
                            {
                                "detail": f"Cannot safely stop the application while '{binding.service_key}' is {service_status}.",
                                "service_key": binding.service_key,
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                instance.status = ApplicationStatus.STOPPING
                instance.stage = "stopping_services"
                instance.runtime_operation = "stop"
                instance.runtime_operation_generation = int(instance.runtime_operation_generation or 0) + 1
                instance.error_code = ""
                instance.error_message = ""
                instance.save(update_fields=[
                    "status", "stage", "runtime_operation",
                    "runtime_operation_generation", "error_code",
                    "error_message", "updated_at",
                ])
                operation_generation = int(instance.runtime_operation_generation)

            try:
                stop_application_runtime.delay(str(instance.pk), operation_generation)
            except Exception:
                # The durable STOPPING state is resumed by the periodic
                # application reconciler after a transient broker outage.
                logger.exception("Unable to enqueue Stop All for application %s", instance.pk)

            instance.refresh_from_db()
            return Response(
                ApplicationInstanceSerializer(instance).data,
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception:
            logger.exception("Ready App Stop All failed for %s", pk)
            return Response(
                {"detail": "The application could not be queued for shutdown."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )



class ApplicationInstanceCancelAPIView(CatalogPermissionMixin, APIView):
    def post(self, request, pk):
        instance = get_object_or_404(ApplicationInstance.objects.filter(user=request.user), pk=pk)
        if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.STOPPING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED} or instance.runtime_operation:
            return Response(ApplicationInstanceSerializer(instance).data, status=status.HTTP_409_CONFLICT)
        from django.db import transaction
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=instance.pk)
            if locked.status in {ApplicationStatus.RUNNING, ApplicationStatus.STOPPING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED} or locked.runtime_operation:
                return Response(ApplicationInstanceSerializer(locked).data, status=status.HTTP_409_CONFLICT)
            locked.cancel_requested = True
            locked.stage = "cancellation_requested"
            locked.save(update_fields=["cancel_requested", "stage", "updated_at"])
            instance = locked
        try:
            cancel_application_installation.delay(str(instance.pk), "Application deployment cancelled by user request.")
        except Exception:
            # The cancellation task only changes application/child cancellation
            # state; apply the same state transition synchronously if the broker
            # is unavailable so an accepted cancel request cannot strand work.
            from .executor import ApplicationStackExecutor
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Unable to queue application cancellation %s; applying synchronously", instance.pk)
            ApplicationStackExecutor(str(instance.pk)).cancel(
                reason="Application deployment cancelled by user request."
            )
        instance.refresh_from_db()
        return Response(ApplicationInstanceSerializer(instance).data, status=status.HTTP_202_ACCEPTED)
