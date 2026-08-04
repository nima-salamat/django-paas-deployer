import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Service, Volume, PrivateNetwork
from deployments.core.deploy import Deploy as Deployer
from deployments.core.manager.container_manager import Container
from deployments.core.manager.volume_manager import Volume as DockerVolume
from deployments.core.manager.image_manager import Image
from deployments.core.manager.network_manager import Network
from core.global_settings.config import PlanTypeChoices

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=Service)
def delete_deploy_before_delete_service(sender, instance: Service, **kwargs):
    """
    Remove Docker resources before deleting the Service.

    DATABASE:
        - Stop container if running.
        - Remove container (volumes are cleaned later if orphaned).

    APPLICATION:
        - Stop + remove container.
        - Optionally remove image (kept conservative: only remove if no other
          services reference the same image name pattern).
    """
    service_name = instance.get_docker_service_name()
    logger.info("pre_delete Service '%s' → cleaning Docker resources for '%s'", instance.name, service_name)

    try:
        container = Container(name=service_name)

        # Always try to stop if it exists and is running
        if container.exists():
            if container.is_running():
                logger.info("Stopping running container '%s'...", service_name)
                try:
                    container.stop(timeout=10)
                except Exception:
                    logger.exception("Failed to stop container '%s' (continuing with remove)", service_name)

            logger.info("Removing container '%s'...", service_name)
            try:
                container.remove()
            except Exception:
                logger.exception("Failed to remove container '%s'", service_name)
        else:
            logger.info("Container '%s' does not exist; nothing to stop/remove.", service_name)

        # For application plans we also try to clean the image that belongs to this service
        if getattr(instance, "plan", None) and instance.plan.plan_type != PlanTypeChoices.DATABASE:
            # Image name convention used by the orchestrator is usually the container name
            try:
                Image.remove_by_name(service_name)
                # also try with :latest if tagged that way
                Image.remove_by_name(f"{service_name}:latest")
            except Exception:
                logger.exception("Failed to remove image for service '%s'", service_name)

    except Exception:
        logger.exception(
            "Failed cleaning docker resources for service '%s' (name=%s).",
            service_name,
            instance.name,
        )

    finally:
        _cleanup_orphaned_volumes(instance)


def _cleanup_orphaned_volumes(service: Service) -> None:
    """
    Detach this service from all volumes and delete any volume that becomes
    completely unattached (both in DB and in Docker).
    """
    service_id = str(service.id)

    # We iterate over a snapshot so we can safely delete
    volumes = list(Volume.objects.filter(user=service.user))

    for volume in volumes:
        changed = False
        attachments = dict(volume.service_attachments or {})

        if service_id in attachments:
            del attachments[service_id]
            volume.service_attachments = attachments
            changed = True

        if volume.service_id == service.id:
            volume.service = None
            changed = True

        if changed:
            volume.save(update_fields=["service_attachments", "service"])

        # Still attached to other services → keep it
        if volume.service_attachments:
            continue

        # Orphaned → remove Docker volume then DB record
        try:
            docker_volume = DockerVolume(volume.get_docker_volume_name())
            try:
                docker_volume.remove()
                logger.info("Removed orphaned docker volume '%s'.", volume.name)
            except Exception:
                logger.exception("Failed removing docker volume '%s' (will still delete DB record).", volume.name)

            volume.delete()
            logger.info("Deleted orphaned Volume record '%s'.", volume.name)
        except Exception:
            logger.exception("Failed deleting volume record '%s'.", volume.name)

@receiver(pre_delete, sender=Volume)
def cleanup_volume_on_delete(sender, instance: Volume, **kwargs):

    logger.info("pre_delete Volume '%s' → removing Docker volume", instance.name)
    try:
        docker_volume = DockerVolume(instance.get_docker_volume_name())
        docker_volume.remove()
        logger.info("Docker volume '%s' removed successfully", instance.name)
    except Exception:
        logger.exception(
            "Failed to remove Docker volume '%s' during Volume pre_delete",
            instance.name,
        )

@receiver(pre_delete, sender=PrivateNetwork)
def cleanup_network_on_delete(sender, instance: PrivateNetwork, **kwargs):

    logger.info("pre_delete PrivateNetwork '%s' → removing Docker network", instance.name)
    try:
        if Network.network_exists(instance.name):
            docker_net = Network(name=instance.get_docker_network_name())
            docker_net.remove()
            logger.info("Docker network '%s' removed successfully", instance.name)
        else:
            logger.info("Docker network '%s' does not exist; nothing to remove", instance.name)
    except Exception:
        logger.exception(
            "Failed to remove Docker network '%s' during PrivateNetwork pre_delete",
            instance.name,
        )