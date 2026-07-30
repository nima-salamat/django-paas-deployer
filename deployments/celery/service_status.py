import logging

from django.db import transaction
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
    - transaction.atomic() is inside the methods so existing callers
      (DeployService / StopService) continue to work without changes.
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
        with transaction.atomic():
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

            # Deploy side
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
        Locks the Service row.
        The service is transitioned to STOPPING while the row is locked.

        selected_deploy is intentionally not loaded with select_related()
        because it is nullable and would create a LEFT OUTER JOIN,
        which PostgreSQL does not allow with FOR UPDATE.
        """
        with transaction.atomic():
            try:
                service = (
                    Service.objects
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
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.STOPPED,
            task_id=None,
        )