from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication
from .catalog import ApplicationCatalog, CatalogValidationError
from .models import ApplicationInstance, ApplicationStatus
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
from services.signals import cleanup_service_resources, delete_service_row_after_cleanup
from .tasks import (
    start_application_installation,
    cancel_application_installation,
    delete_application_installation,
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
            instance.save(update_fields=["stage", "error_code", "updated_at"])

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
            variant = str(request.data.get("variant") or "").strip()
            config = request.data.get("config") or {}

            if not name or not plan_id or not variant:
                raise CatalogValidationError("name, plan_id, variant, and config are required.")
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
            plan = Plan.objects.filter(pk=plan_id).first()
            if not plan or str(plan.platform) != "docker":
                raise CatalogValidationError("Selected plan must be a Docker application/ready-made plan.")

            resource_summary = resource_summary_for_resolved(resolved, plan)
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

class ApplicationInstanceCancelAPIView(CatalogPermissionMixin, APIView):
    def post(self, request, pk):
        instance = get_object_or_404(ApplicationInstance.objects.filter(user=request.user), pk=pk)
        if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
            return Response(ApplicationInstanceSerializer(instance).data, status=status.HTTP_409_CONFLICT)
        from django.db import transaction
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=instance.pk)
            if locked.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
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
