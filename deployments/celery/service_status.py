import logging

from django.utils import timezone

from deploy.models import Deploy, DeploymentStatusChoices
from services.models import Service
from core.global_settings.config import SERVICE_STATUS_CHOICES

from .exceptions import InvalidServiceStateError


logger = logging.getLogger(__name__)


class ServiceStateManager:
    """
    Manages transactional database queries and service state transitions.

    Important:
    - All state-changing operations use select_for_update().
    - Related objects that are needed are loaded with select_related()
      in the same query.
    - These methods do NOT open their own transaction.atomic().
      The caller MUST wrap them in transaction.atomic() if the lock
      needs to be held across subsequent operations.
    """

    @classmethod
    def lock_and_get_deployment(cls, deploy_id: int) -> Deploy:
        """
        Locks both the Deploy row and its associated Service row.

        The service must currently be QUEUED before deployment starts.
        Transitions:
          - Service.status  → DEPLOYING
          - Deploy.status   → RUNNING (and sets started_at)
        """
        try:
            deploy_item = (
                Deploy.objects
                .select_related(
                    "service",
                    "service__plan",
                    "service__network",
                )
                .select_for_update(
                    of=("self", "service"),
                )
                .get(pk=deploy_id)
            )
        except Deploy.DoesNotExist as exc:
            raise InvalidServiceStateError(
                f"Deploy ID {deploy_id} does not exist."
            ) from exc

        service = deploy_item.service

        if service.status != SERVICE_STATUS_CHOICES.QUEUED:
            raise InvalidServiceStateError(
                f"Deploy aborted. "
                f"Service status is {service.status}, "
                f"expected QUEUED."
            )

        # Service side
        service.status = SERVICE_STATUS_CHOICES.DEPLOYING
        service.deploy_started = timezone.now()
        service.save(update_fields=["status", "deploy_started"])

        # Deploy side (only existing fields)
        deploy_item.status = DeploymentStatusChoices.RUNNING
        deploy_item.started_at = timezone.now()
        deploy_item.stage = "starting"
        deploy_item.progress = 0
        deploy_item.save(
            update_fields=["status", "started_at", "stage", "progress"]
        )

        return deploy_item

    @classmethod
    def lock_and_start_stopping(cls, service_id: int) -> Service:
        """
        Locks the Service row and loads selected_deploy in the same query.

        The service is transitioned to STOPPING while the row is locked.
        """
        try:
            service = (
                Service.objects
                .select_related("selected_deploy")
                .select_for_update()
                .get(pk=service_id)
            )
        except Service.DoesNotExist as exc:
            raise InvalidServiceStateError(
                f"Service ID {service_id} does not exist."
            ) from exc

        service.status = SERVICE_STATUS_CHOICES.STOPPING
        service.save(update_fields=["status"])

        return service

    @classmethod
    def sync_legacy_success(
        cls,
        service_id: int,
        deploy_id: int | None = None,
    ) -> None:
        """
        Synchronizes legacy service tracking fields after successful deployment.
        Optionally updates the related Deploy record as well.
        """
        now = timezone.now()

        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.SUCCEEDED,
            deployed_at=now,
            deploy_started=None,
            task_id=None,
        )

        if deploy_id is not None:
            Deploy.objects.filter(pk=deploy_id).update(
                status=DeploymentStatusChoices.SUCCEEDED,
                completed_at=now,
                progress=100,
                stage="finished",
            )

    @classmethod
    def sync_legacy_failure(
        cls,
        service_id: int,
        deploy_id: int | None = None,
    ) -> None:
        """
        Synchronizes legacy service tracking fields after deployment failure.
        """
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )

        if deploy_id is not None:
            Deploy.objects.filter(pk=deploy_id).update(
                status=DeploymentStatusChoices.FAILED,
                completed_at=timezone.now(),
            )

    @classmethod
    def sync_legacy_stopped(cls, service_id: int) -> None:
        """
        Synchronizes legacy service tracking fields after successful stop.
        """
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.STOPPED,
            task_id=None,
        )