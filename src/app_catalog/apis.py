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
from .tasks import (
    start_application_installation,
    cancel_application_installation,
    delete_application_installation,
)


def _queue_ready_app_deletion(instance_id: str) -> None:
    """Converge deletion immediately, then persist a durable retry."""
    from django.utils import timezone

    instance = ApplicationInstance.objects.filter(pk=instance_id).first()
    if instance is None:
        return

    ApplicationInstance.objects.filter(pk=instance_id).update(
        stage="deletion_pending",
        error_code="APPLICATION_DELETION_PENDING",
        updated_at=timezone.now(),
    )

    # Do not make cancellation dependent on Celery availability. This bounded
    # coordinator attempt cancels active child Deploys and performs any safe
    # synchronous cleanup; the durable task remains responsible for retries.
    try:
        from .executor import ApplicationStackExecutor

        ApplicationStackExecutor(str(instance_id)).cleanup_terminal_application()
    except Exception:
        logger = __import__("logging").getLogger(__name__)
        logger.exception(
            "Immediate Ready App deletion convergence failed for %s; keeping durable retry.",
            instance_id,
        )

    if not ApplicationInstance.objects.filter(pk=instance_id).exists():
        return

    try:
        delete_application_installation.delay(str(instance_id))
    except Exception:
        # The reconciliation scheduler retries stale deletion_pending rows, so
        # a temporary broker outage must not strand the installation.
        logger = __import__("logging").getLogger(__name__)
        logger.exception("Unable to queue Ready App deletion %s", instance_id)


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

        if instance.status == ApplicationStatus.CANCELLED and instance.cancel_requested:
            # DELETE on a cancelled installation is allowed to finish its own
            # cancellation/cleanup flow. Propagate the cancellation again in
            # case a child deployment was slow or the original cancel worker
            # was lost. We never delete a live child runtime.
            from .executor import ApplicationStackExecutor
            try:
                ApplicationStackExecutor(str(instance.pk)).cancel(
                    reason=instance.error_message or "Application deployment cancelled."
                )
                instance.refresh_from_db()
                active_children = [
                    row for row in instance.services.select_related("deploy").all()
                    if row.deploy.status in {"pending", "running", "rolling_back"}
                ]
            except Exception as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.exception("Ready App cancellation propagation failed for %s", instance.pk)
                return Response(
                    {
                        "error": "Cancellation cleanup could not be continued safely.",
                        "code": "application_cleanup_failed",
                        "detail": str(exc),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        if active_children:
            _queue_ready_app_deletion(instance.pk)
            return Response(
                {
                    "error": "Cleanup is still in progress.",
                    "code": "application_cleanup_pending",
                    "detail": (
                        "The application has been marked for deletion. PassDeployer is "
                        "stopping active child deployments and will retry cleanup automatically."
                    ),
                    "active_service_count": len(active_children),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # A cancelled installation may reach this endpoint before its
        # asynchronous cleanup callback. Make deletion self-healing by running
        # the same normal Service/resource cleanup synchronously.
        if instance.status == ApplicationStatus.CANCELLED and instance.cancel_requested:
            from .executor import ApplicationStackExecutor
            try:
                ApplicationStackExecutor(str(instance.pk))._cleanup_cancelled_children()
                instance.refresh_from_db()
            except Exception as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.exception("Ready App deletion cleanup failed for %s", instance.pk)
                _queue_ready_app_deletion(instance.pk)
                return Response(
                    {
                        "error": "The installation is queued for cleanup.",
                        "code": "application_cleanup_pending",
                        "detail": str(exc),
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

        # Preflight every Service that belongs to this application's private
        # network. Binding rows are authoritative, while the application-owned
        # network plus catalog metadata recover legacy orphaned child Services
        # left behind by an earlier partial deletion.
        from django.db import transaction
        from deploy.models import Deploy
        from services.models import PrivateNetwork, ServiceNetworkAttachment
        from services.signals import cleanup_service_resources
        from .services import application_services_for_cleanup

        service_bindings, service_rows, unexpected_services = application_services_for_cleanup(instance)
        if unexpected_services:
            names = ", ".join(str(service.name) for service in unexpected_services[:5])
            suffix = "..." if len(unexpected_services) > 5 else ""
            return Response(
                {
                    "error": "The installation's private network is still used by another service.",
                    "code": "application_cleanup_pending",
                    "detail": (
                        f"Cannot safely delete the network until these service attachments are "
                        f"removed or detached: {names}{suffix}"
                    ),
                    "blocked_service_count": len(unexpected_services),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            for service in service_rows:
                cleanup_service_resources(service)
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Ready App resource preflight failed for %s", instance.pk)
            _queue_ready_app_deletion(instance.pk)
            return Response(
                {
                    "error": "The installation is queued for cleanup.",
                    "code": "application_cleanup_pending",
                    "detail": str(exc),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # Perform all database deletion under one transaction. Locking the
        # application/network closes the gap where another worker could attach
        # a Service between the preflight and PrivateNetwork.delete().
        try:
            with transaction.atomic():
                locked_instance = (
                    ApplicationInstance.objects
                    .select_for_update()
                    .get(pk=instance.pk)
                )
                locked_network = (
                    PrivateNetwork.objects
                    .select_for_update()
                    .filter(pk=locked_instance.network_id)
                    .first()
                )
                if locked_network is not None:
                    _, locked_service_rows, unexpected_services = application_services_for_cleanup(locked_instance)
                    if unexpected_services:
                        names = ", ".join(str(service.name) for service in unexpected_services[:5])
                        suffix = "..." if len(unexpected_services) > 5 else ""
                        return Response(
                            {
                                "error": "The installation's private network is still used by another service.",
                                "code": "application_cleanup_pending",
                                "detail": (
                                    f"Cannot safely delete the network until these service attachments are "
                                    f"removed or detached: {names}{suffix}"
                                ),
                                "blocked_service_count": len(unexpected_services),
                            },
                            status=status.HTTP_202_ACCEPTED,
                        )
                    service_rows = locked_service_rows
                else:
                    service_rows = list(
                        Service.objects.filter(
                            user_id=locked_instance.user_id,
                            pk__in=[binding.service_id for binding in service_bindings],
                        )
                    )

                bindings_by_service = {
                    str(binding.service_id): binding
                    for binding in service_bindings
                }
                for service in service_rows:
                    for deploy in Deploy.objects.filter(service_id=service.pk).only("zip_file"):
                        if deploy.zip_file and deploy.zip_file.name:
                            try:
                                deploy.zip_file.delete(save=False)
                            except Exception:
                                logger = __import__("logging").getLogger(__name__)
                                logger.exception(
                                    "Failed deleting deployment archive for service %s.",
                                    service.pk,
                                )
                    binding = bindings_by_service.get(str(service.pk))
                    if binding is not None:
                        binding.delete()
                    if Service.objects.filter(pk=service.pk).exists():
                        service.delete()

                if locked_network is not None:
                    if (
                        Service.objects.filter(network_id=locked_network.pk).exists()
                        or ServiceNetworkAttachment.objects.filter(network_id=locked_network.pk).exists()
                    ):
                        raise RuntimeError(
                            f"Private network '{locked_network.name}' is still referenced after "
                            "all owned child services were deleted."
                        )
                    locked_network.delete()

                locked_instance.network = None
                locked_instance.save(update_fields=["network", "updated_at"])
                locked_instance.delete()
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Ready App database deletion failed for %s", instance.pk)
            _queue_ready_app_deletion(instance.pk)
            return Response(
                {
                    "error": "The installation is queued for cleanup.",
                    "code": "application_cleanup_pending",
                    "detail": str(exc),
                },
                status=status.HTTP_202_ACCEPTED,
            )
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
