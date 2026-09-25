from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication
from .catalog import ApplicationCatalog, CatalogValidationError, redact_resolved, redacted_definition, resolve_variant
from .models import ApplicationInstance, ApplicationStatus
from .serializers import ApplicationInstanceSerializer, catalog_listing
from .services import create_application_installation
from .tasks import start_application_installation, cancel_application_installation


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
        return Response(redacted_definition(definition))


class CatalogResolveAPIView(CatalogPermissionMixin, APIView):
    def post(self, request, catalog_id):
        try:
            definition = ApplicationCatalog.get(catalog_id)
            variant = str(request.data.get("variant") or "")
            resolved = resolve_variant(definition, variant, request.data.get("config") or {})
            return Response(redact_resolved(resolved))
        except (KeyError, CatalogValidationError) as exc:
            return Response({"error": str(exc)}, status=400)


class ApplicationInstanceListCreateAPIView(CatalogPermissionMixin, APIView):
    def get(self, request):
        rows = ApplicationInstance.objects.filter(user=request.user).prefetch_related("services__service", "services__deploy")
        return Response(ApplicationInstanceSerializer(rows, many=True).data)

    def post(self, request):
        try:
            instance = create_application_installation(request.user, request.data)
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
            ApplicationInstance.objects.filter(user=request.user).prefetch_related("services__deploy"),
            pk=pk,
        )
        terminal = {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}
        if instance.status not in terminal:
            return Response(
                {
                    "error": "Application must be in a terminal state before deletion.",
                    "code": "application_not_terminal",
                    "status": instance.status,
                },
                status=status.HTTP_409_CONFLICT,
            )
        active_children = [
            row for row in instance.services.select_related("deploy").all()
            if row.deploy.status in {"pending", "running", "rolling_back"}
        ]
        if active_children:
            return Response(
                {
                    "error": "Application still has active service deployments.",
                    "code": "application_children_active",
                },
                status=status.HTTP_409_CONFLICT,
            )
        # Delete child services first. Their pre_delete handlers remove
        # containers/volumes before the application-owned Docker network is
        # deleted; relying on Django CASCADE ordering could otherwise attempt
        # to remove an attached network too early and leak it.
        service_rows = list(instance.services.select_related("service").all())
        network = instance.network
        for row in service_rows:
            row.service.delete()
        if network is not None:
            network.delete()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
