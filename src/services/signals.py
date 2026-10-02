import logging

import docker.errors

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models import Service, ServiceRevision, ServiceNetworkAttachment, Volume, PrivateNetwork
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import SwarmRuntime, swarm_enabled
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
        if swarm_enabled():
            try:
                SwarmRuntime().remove_service_group(str(service.pk))
            except Exception as exc:
                logger.exception(
                    "Failed cleaning Docker Swarm services for service '%s'.",
                    service.name,
                )
                raise RuntimeError(
                    f"Failed to remove Swarm runtime for service '{service.name}'."
                ) from exc

        container = Container(name=service_name)

        if container.exists():
            raw = container.client.containers.get(service_name)
            labels = dict(getattr(raw, "labels", {}) or {})
            expected_service = str(service.pk)
            expected_deploy = str(getattr(instance.selected_deploy, "pk", "") or "")
            managed = labels.get("managed-by") in {"django-paas-deployer", "passdeployer"}
            owns_service = managed and labels.get("service.id") == expected_service
            owns_selected_deploy = expected_deploy and labels.get("deployment.id") == expected_deploy
            if not (owns_service or owns_selected_deploy):
                logger.error(
                    "Refusing to remove container '%s' during Service deletion: "
                    "Docker ownership labels do not match service=%s/deploy=%s.",
                    service_name, expected_service, expected_deploy or "<none>",
                )
                raise RuntimeError(
                    f"Refusing to delete service '{service.name}': "
                    f"container '{service_name}' exists but is not owned by PassDeployer."
                )
            else:
                if container.is_running():
                    logger.info("Stopping running container '%s'...", service_name)
                    try:
                        container.stop(timeout=10)
                    except Exception:
                        logger.exception(
                            "Failed to stop container '%s' (continuing with remove)",
                            service_name,
                        )

                logger.info("Removing owned container '%s'...", service_name)
                try:
                    container.remove()
                except Exception:
                    logger.exception("Failed to remove owned container '%s'", service_name)
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
        docker_name = volume.get_docker_volume_name()
        try:
            docker_volume = DockerVolume(docker_name)
            try:
                raw_volume = docker_volume.client.volumes.get(docker_name)
            except docker.errors.NotFound:
                raw_volume = None
            if raw_volume is not None:
                labels = dict(getattr(raw_volume, "attrs", {}).get("Labels") or {})
                if labels.get("managed-by") != "django-paas-deployer":
                    raise RuntimeError(
                        f"Refusing to remove Docker volume '{volume.name}': ownership label is missing or unexpected."
                    )
                docker_volume.remove()
                logger.info(
                    "Removed Docker volume '%s' for deleted service '%s'.",
                    volume.name,
                    service.name,
                )
        except docker.errors.NotFound:
            pass
        except Exception:
            logger.exception(
                "Failed removing Docker volume '%s'; DB record will be retained to prevent invisible storage drift.",
                volume.name,
            )
            raise

        volume.delete()
        logger.info(
            "Deleted Volume record '%s' owned by service '%s'.",
            volume.name,
            service.name,
        )


@receiver(pre_delete, sender=Volume)
def cleanup_volume_on_delete(sender, instance: Volume, **kwargs):
    """Remove the underlying Docker volume when a Volume row is deleted."""
    logger.info(
        "pre_delete Volume '%s' → removing Docker volume", instance.name
    )
    try:
        docker_volume = DockerVolume(instance.get_docker_volume_name())
        try:
            raw_volume = docker_volume.client.volumes.get(instance.get_docker_volume_name())
        except docker.errors.NotFound:
            logger.info("Docker volume '%s' is already absent.", instance.name)
            return
        labels = dict(getattr(raw_volume, "attrs", {}).get("Labels") or {})
        if labels.get("managed-by") != "django-paas-deployer":
            raise RuntimeError(
                f"Refusing to remove Docker volume '{instance.name}': ownership label is missing or unexpected."
            )
        docker_volume.remove()
        logger.info("Docker volume '%s' removed successfully", instance.name)
    except docker.errors.NotFound:
        return
    except Exception:
        logger.exception(
            "Failed to remove Docker volume '%s' during Volume pre_delete; refusing to delete the DB row.",
            instance.name,
        )
        raise


@receiver(pre_delete, sender=PrivateNetwork)
def cleanup_network_on_delete(sender, instance: PrivateNetwork, **kwargs):
    """Remove the owned Docker network when a PrivateNetwork row is deleted."""
    logger.info(
        "pre_delete PrivateNetwork '%s' → removing owned Docker network",
        instance.name,
    )
    try:
        docker_name = instance.get_docker_network_name()
        if not Network.network_exists(docker_name):
            logger.info("Owned Docker network '%s' does not exist; nothing to remove", docker_name)
            return

        docker_network = Network(name=docker_name)
        raw = docker_network.client.networks.get(docker_name)
        labels = dict(getattr(raw, "attrs", {}).get("Labels") or {})
        if labels.get("managed-by") != "django-paas-deployer":
            logger.error(
                "Refusing to remove Docker network '%s': ownership label is missing or unexpected.",
                docker_name,
            )
            return
        docker_network.remove()
        logger.info("Owned Docker network '%s' removed successfully", docker_name)
    except Exception:
        logger.exception(
            "Failed to remove owned Docker network for PrivateNetwork '%s'",
            instance.name,
        )
