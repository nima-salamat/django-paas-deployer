import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Service, Volume
from deployments.core.deploy import Deploy as Deployer
from deployments.core.manager.container_manager import Container
from deployments.core.manager.volume_manager import Volume as DockerVolume
from core.global_settings.config import PlanTypeChoices

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=Service)
def delete_deploy_before_delete_service(sender, instance: Service, **kwargs):
    """
    Remove Docker resources before deleting the Service.

    DATABASE:
        - Stop container only if it is running.
        - Remove container.

    APPLICATION:
        - Remove container only.
        - Preserve image.
    """

    service_name = instance.get_docker_service_name()

    try:
        if instance.plan.plan_type == PlanTypeChoices.DATABASE:
            container = Container(service_name)

            if container.is_running():
                logger.info(
                    "Stopping running database container '%s'...",
                    service_name,
                )
                container.stop(timeout=5)

            logger.info(
                "Removing database container '%s'...",
                service_name,
            )
            container.remove()

        else:
            # APP
            logger.info(
                "Removing application container '%s'...",
                service_name,
            )
            Deployer.remove_container_only(service_name)

    except Exception:
        logger.exception(
            "Failed cleaning docker resources for service '%s'.",
            service_name,
        )

    finally:
        _cleanup_orphaned_volumes(instance)


def _cleanup_orphaned_volumes(service: Service) -> None:
    """
    Delete Docker volumes that are no longer attached to any service.
    """

    service_id = str(service.id)

    for volume in Volume.objects.filter(user=service.user):

        changed = False
        attachments = volume.service_attachments.copy()

        if service_id in attachments:
            del attachments[service_id]
            volume.service_attachments = attachments
            changed = True

        if volume.service_id == service.id:
            volume.service = None
            changed = True

        if changed:
            volume.save(update_fields=["service_attachments", "service"])

        if volume.service_attachments:
            continue

        try:
            docker_volume = DockerVolume(volume.name)

            try:
                docker_volume.remove()
                logger.info(
                    "Removed orphaned docker volume '%s'.",
                    volume.name,
                )
            except Exception:
                logger.exception(
                    "Failed removing docker volume '%s'.",
                    volume.name,
                )

            volume.delete()

        except Exception:
            logger.exception(
                "Failed deleting volume record '%s'.",
                volume.name,
            )