import logging
import os
import shutil

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from users.models import User, Profile
from services.models import Service, Volume, PrivateNetwork
from deploy.models import Deploy
from deployments.core.manager.container_manager import Container
from deployments.core.manager.volume_manager import Volume as DockerVolume
from deployments.core.manager.network_manager import Network as DockerNetwork
from deployments.core.manager.image_manager import Image
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer
from core.global_settings.config import PlanTypeChoices

logger = logging.getLogger(__name__)


def _resolve_platform(deploy):
    cfg = deploy.config or {}
    if isinstance(cfg, str):
        import json
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    service = getattr(deploy, "service", None)
    plan = getattr(service, "plan", None) if service else None
    if plan and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    return "docker"


@receiver(pre_delete, sender=User)
def cleanup_user_resources(sender, instance: User, **kwargs):
    user_id = instance.id
    logger.info("=== pre_delete User %s (id=%s) → full cleanup started ===", instance, user_id)


    services = list(Service.objects.filter(user=instance).select_related("plan", "selected_deploy"))

    for service in services:
        container_name = service.get_docker_service_name()
        logger.info("Cleaning service '%s' → container '%s'", service.name, container_name)

        try:
            is_db = (
                getattr(service.plan, "plan_type", None) == PlanTypeChoices.DATABASE
                or (service.selected_deploy and _resolve_platform(service.selected_deploy) in DB_PLATFORMS)
            )

            if is_db:
                try:
                    DBDeployer().remove(container_name)
                except Exception:
                    logger.exception("DBDeployer.remove failed for %s", container_name)
                    c = Container(name=container_name)
                    if c.exists():
                        if c.is_running():
                            c.stop(timeout=10)
                        c.remove()
            else:
                try:
                    OrchestratorDeploy.remove_all(container_name)
                except Exception:
                    logger.exception("OrchestratorDeploy.remove_all failed for %s", container_name)
                    c = Container(name=container_name)
                    if c.exists():
                        if c.is_running():
                            c.stop(timeout=10)
                        c.remove()
                    Image.remove_by_name(container_name)
                    Image.remove_by_name(f"{container_name}:latest")

        except Exception:
            logger.exception("Failed to clean Docker resources for service '%s'", service.name)


    volumes = list(Volume.objects.filter(user=instance))
    for volume in volumes:
        try:
            docker_vol = DockerVolume(volume.name)
            docker_vol.remove()
            logger.info("Removed Docker volume '%s'", volume.name)
        except Exception:
            logger.exception("Failed to remove Docker volume '%s'", volume.name)


    networks = list(PrivateNetwork.objects.filter(user=instance))
    for net in networks:
        try:
            if DockerNetwork.network_exists(net.name):
                docker_net = DockerNetwork(name=net.name)
                docker_net.remove()
                logger.info("Removed Docker network '%s'", net.name)
        except Exception:
            logger.exception("Failed to remove Docker network '%s'", net.name)

    profiles = list(Profile.objects.filter(user=instance))
    for profile in profiles:
        if profile.image:
            try:
                profile.image.delete(save=False)
                logger.info("Deleted profile image for user %s (profile id=%s)", user_id, profile.pk)
            except Exception:
                logger.exception(
                    "Failed to delete profile image for user %s (profile id=%s)",
                    user_id, profile.pk
                )

    try:
        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root:
            user_deploy_dir = os.path.join(media_root, "deployments", str(user_id))
            if os.path.isdir(user_deploy_dir):
                shutil.rmtree(user_deploy_dir, ignore_errors=True)
                logger.info("Removed user deployment directory: %s", user_deploy_dir)
    except Exception:
        logger.exception("Failed to remove user deployment directory for user_id=%s", user_id)

    logger.info("=== pre_delete User %s finished ===", user_id)


@receiver(pre_delete, sender=Profile)
def cleanup_profile_image(sender, instance: Profile, **kwargs):
    if instance.image:
        try:
            instance.image.delete(save=False)
            logger.info("Deleted profile image: %s", instance.image.name)
        except Exception:
            logger.exception(
                "Failed to delete profile image: %s",
                getattr(instance.image, "name", None)
            )