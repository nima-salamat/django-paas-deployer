import logging
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Service, Volume
from deployments.core.deploy import Deploy as Deployer
from deployments.core.manager.container_manager import Container
from deployments.core.manager.volume_manager import Volume as DockerVolume
from core.global_settings.config import PlanTypeChoices

logger = logging.getLogger(__name__)


@receiver(signal=pre_delete, sender=Service)
def delete_deploy_before_delete_service(sender, instance, **kwargs):
    """
    Clean up Docker resources when a Service is deleted.
    
    For DB platforms: remove container only (preserve image)
    For APP platforms: remove container + image
    """
    service_name = instance.get_docker_service_name()
    
    # Check if this is a DB service based on plan type
    if instance.plan.platform_type == PlanTypeChoices.DATABASE:
        # DB service - remove container only, keep image for rebuilds
        container = Container(service_name)
        if container.exists():
            try:
                container.stop(timeout=5)
                container.remove()
            except Exception as exc:
                logger.warning(f"Failed to remove DB container '{service_name}': {exc}")
    else:
        # APP service - remove container only, preserve image for rebuilds
        Deployer.remove_container_only(service_name)
    
    # Clean up orphaned volumes that belong only to this service
    _cleanup_orphaned_volumes(instance)


def _cleanup_orphaned_volumes(service: Service) -> None:
    """
    Delete Docker volumes that are no longer used by any service.
    Only volumes owned by the same user are considered.
    """
    # Get all volumes attached to this service via service_attachments
    all_volumes = Volume.objects.filter(user=service.user)
    service_id_str = str(service.id)
    
    for volume in all_volumes:
        # Check if volume is attached to this service
        if service_id_str in volume.service_attachments:
            # Remove this service from attachments
            attachments = volume.service_attachments.copy()
            if service_id_str in attachments:
                del attachments[service_id_str]
                volume.service_attachments = attachments
            
            # If this was the legacy service, clear it
            if volume.service_id == service.id:
                volume.service = None
            
            volume.save()
        
        # Check if volume is now orphaned (no attachments)
        if not volume.service_attachments:
            # Volume is orphaned - remove from Docker
            try:
                docker_vol = DockerVolume(volume.name)
                if docker_vol.exists():
                    docker_vol.remove(force=True)
                    logger.info(f"Removed orphaned volume '{volume.name}'")
                # Also delete the database record
                volume.delete()
            except Exception as exc:
                logger.warning(f"Failed to remove orphaned volume '{volume.name}': {exc}")