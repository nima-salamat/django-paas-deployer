import logging
from django.db import transaction
from deploy.models import Deploy
from services.models import Service
from core.global_settings.config import SERVICE_STATUS_CHOICES
from .exceptions import InvalidServiceStateError

logger = logging.getLogger(__name__)

# deployments/celery/service_status.py

class ServiceStateManager:
    """Manages transactional database queries and initial state checks."""

    @classmethod
    def lock_and_get_deployment(cls, deploy_id: int) -> Deploy:
        """
        Acquires a row lock on the deployment item and verifies that 
        the associated service is currently QUEUED for deployment.
        """
        with transaction.atomic():
            try:
                deploy_item = Deploy.objects.select_for_update(of=('self',)).select_related(
                    "service", "service__plan", "service__network"
                ).get(pk=deploy_id)
            except Deploy.DoesNotExist as exc:
                raise InvalidServiceStateError(f"Deploy ID {deploy_id} does not exist.") from exc

            if deploy_item.service.status != SERVICE_STATUS_CHOICES.QUEUED:
                raise InvalidServiceStateError(
                    f"Deploy aborted. Service status is {deploy_item.service.status}, expected QUEUED."
                )

            # Sync legacy status tracking field alongside new state tracker
            deploy_item.service.status = SERVICE_STATUS_CHOICES.DEPLOYING
            deploy_item.service.save(update_fields=["status"])
            
            return deploy_item

    @classmethod
    def lock_and_start_stopping(cls, service_id: int) -> Service:
        """Locks the service and transitions its state to STOPPING."""
        with transaction.atomic():
            try:
                service = Service.objects.select_for_update().select_related("selected_deploy").get(pk=service_id)
            except Service.DoesNotExist as exc:
                raise InvalidServiceStateError(f"Service ID {service_id} does not exist.") from exc

            service.status = SERVICE_STATUS_CHOICES.STOPPING
            service.save(update_fields=["status"])
            return service

    @classmethod
    def sync_legacy_success(cls, service_id: int) -> None:
        """Synchronizes legacy service tracking fields upon successful completion."""
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.SUCCEEDED
        )

    @classmethod
    def sync_legacy_failure(cls, service_id: int) -> None:
        """Synchronizes legacy service tracking fields upon a failure path."""
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.FAILED
        )

    @classmethod
    def sync_legacy_stopped(cls, service_id: int) -> None:
        """Synchronizes legacy service tracking fields upon a successful stop."""
        Service.objects.filter(pk=service_id).update(
            status=SERVICE_STATUS_CHOICES.STOPPED
        )