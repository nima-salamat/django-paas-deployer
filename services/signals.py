import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Service, Volume, PrivateNetwork
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
        - Remove container (volumes owned by this service are cleaned below).

    APPLICATION:
        - Stop + remove container.
        - Remove image associated with this service name.
    """
    service_name = instance.get_docker_service_name()
    logger.info(
        "pre_delete Service '%s' → cleaning Docker resources for '%s'",
        instance.name,
        service_name,
    )

    try:
        container = Container(name=service_name)

        if container.exists():
            if container.is_running():
                logger.info("Stopping running container '%s'...", service_name)
                try:
                    container.stop(timeout=10)
                except Exception:
                    logger.exception(
                        "Failed to stop container '%s' (continuing with remove)",
                        service_name,
                    )

            logger.info("Removing container '%s'...", service_name)
            try:
                container.remove()
            except Exception:
                logger.exception("Failed to remove container '%s'", service_name)
        else:
            logger.info(
                "Container '%s' does not exist; nothing to stop/remove.",
                service_name,
            )

        # Application plans: remove image built for this service
        if getattr(instance, "plan", None) and getattr(
            instance.plan, "plan_type", None
        ) != PlanTypeChoices.DATABASE:
            try:
                Image.remove_by_name(service_name)
                Image.remove_by_name(f"{service_name}:latest")
            except Exception:
                logger.exception(
                    "Failed to remove image for service '%s'", service_name
                )

    except Exception:
        logger.exception(
            "Failed cleaning docker resources for service '%s' (name=%s).",
            service_name,
            instance.name,
        )

    finally:
        # Volumes are exclusive to this service — delete them (Docker + DB)
        _cleanup_service_volumes(instance)


def _cleanup_service_volumes(service: Service) -> None:
    """
    With exclusive ownership, every volume with service_id == this service
    is deleted (Docker volume + DB row). There is no multi-service sharing.
    """
    volumes = list(Volume.objects.filter(service_id=service.pk))

    for volume in volumes:
        # Remove Docker volume first
        try:
            docker_volume = DockerVolume(volume.get_docker_volume_name())
            try:
                docker_volume.remove()
                logger.info(
                    "Removed Docker volume '%s' for deleted service '%s'.",
                    volume.name,
                    service.name,
                )
            except Exception:
                logger.exception(
                    "Failed removing Docker volume '%s' (will still delete DB record).",
                    volume.name,
                )
        except Exception:
            logger.exception(
                "Could not resolve Docker volume for '%s'.", volume.name
            )

        # Delete DB record (avoids cascading surprises if CASCADE is not set)
        try:
            volume.delete()
            logger.info(
                "Deleted Volume record '%s' owned by service '%s'.",
                volume.name,
                service.name,
            )
        except Exception:
            logger.exception(
                "Failed deleting volume record '%s'.", volume.name
            )


@receiver(pre_delete, sender=Volume)
def cleanup_volume_on_delete(sender, instance: Volume, **kwargs):
    """Remove the underlying Docker volume when a Volume row is deleted."""
    logger.info(
        "pre_delete Volume '%s' → removing Docker volume", instance.name
    )
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
    """Remove the Docker network when a PrivateNetwork row is deleted."""
    logger.info(
        "pre_delete PrivateNetwork '%s' → removing Docker network",
        instance.name,
    )
    try:
        docker_name = instance.get_docker_network_name()
        if Network.network_exists(docker_name):
            docker_net = Network(name=docker_name)
            docker_net.remove()
            logger.info(
                "Docker network '%s' removed successfully", docker_name
            )
        else:
            # Fallback: some code paths used plain name
            if Network.network_exists(instance.name):
                docker_net = Network(name=instance.name)
                docker_net.remove()
                logger.info(
                    "Docker network '%s' removed successfully", instance.name
                )
            else:
                logger.info(
                    "Docker network '%s' does not exist; nothing to remove",
                    docker_name,
                )
    except Exception:
        logger.exception(
            "Failed to remove Docker network for PrivateNetwork '%s'",
            instance.name,
        )
