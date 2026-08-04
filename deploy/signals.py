import logging
import os

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Deploy
from services.models import Service
from deployments.core.manager.container_manager import Container
from deployments.core.manager.image_manager import Image
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer

logger = logging.getLogger(__name__)


def _resolve_platform(deploy: Deploy) -> str:
    """Same logic used in services/apis.py."""
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
    plan = getattr(service, "plan", None) if service is not None else None
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    return "docker"


@receiver(pre_delete, sender=Deploy)
def cleanup_deploy_resources(sender, instance: Deploy, **kwargs):
    """
    1. Always remove the uploaded ZIP file.
    2. If this Deploy is currently selected by a Service, stop + remove the
       corresponding container (and image for non-DB platforms).
    """
    # ------------------------------------------------------------------
    # 1. ZIP file
    # ------------------------------------------------------------------
    if instance.zip_file and getattr(instance.zip_file, "path", None):
        try:
            if os.path.isfile(instance.zip_file.path):
                os.remove(instance.zip_file.path)
                logger.info("Removed zip file for Deploy '%s'", instance.name)
        except Exception:
            logger.exception("Failed to remove zip file for Deploy '%s'", instance.name)

    # ------------------------------------------------------------------
    # 2. Docker resources when this Deploy is the selected one
    # ------------------------------------------------------------------
    try:
        # Find services that currently point to this Deploy
        services = Service.objects.filter(selected_deploy=instance).select_related("plan")
        if not services.exists():
            return

        platform = _resolve_platform(instance)
        is_db = platform in DB_PLATFORMS

        for service in services:
            container_name = service.get_docker_service_name()
            logger.info(
                "Deploy '%s' is selected by Service '%s' → cleaning container '%s'",
                instance.name,
                service.name,
                container_name,
            )

            try:
                if is_db:
                    # DBDeployer.remove stops + removes the container (preserves volumes)
                    DBDeployer().remove(container_name)
                else:
                    # Full cleanup for application deploys
                    OrchestratorDeploy.remove_all(container_name)
            except Exception:
                # Fallback to low-level managers if the high-level helper fails
                logger.exception(
                    "High-level cleanup failed for '%s', falling back to Container/Image managers",
                    container_name,
                )
                try:
                    container = Container(name=container_name)
                    if container.exists():
                        if container.is_running():
                            container.stop(timeout=10)
                        container.remove()
                    # Try to remove the image as well
                    Image.remove_by_name(container_name)
                    Image.remove_by_name(f"{container_name}:latest")
                except Exception:
                    logger.exception("Fallback cleanup also failed for '%s'", container_name)

            # Clear the selected_deploy pointer so the service does not keep a dangling FK
            # (the OneToOne is SET_NULL, but we do it explicitly for cleanliness)
            Service.objects.filter(pk=service.pk).update(
                selected_deploy=None,
                selected_deploy_at=None,
            )

    except Exception:
        logger.exception("Unexpected error while cleaning Docker resources for Deploy '%s'", instance.name)