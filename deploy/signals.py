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


def _cleanup_zip_and_dirs(instance: Deploy):
    if not instance.zip_file:
        return

    try:
        file_path = instance.zip_file.path
    except Exception:
        logger.exception(
            "Could not resolve zip file path for Deploy '%s'", instance.name
        )
        return

    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
            logger.info("Removed zip file: %s", file_path)
        except Exception:
            logger.exception("Failed to remove zip file: %s", file_path)
            return
    try:
        deploy_dir = os.path.dirname(file_path)
        user_dir = os.path.dirname(deploy_dir)

        for d in (deploy_dir, user_dir):
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                logger.info("Removed empty directory: %s", d)
    except Exception:
        logger.exception(
            "Failed while cleaning empty directories for Deploy '%s'",
            instance.name,
        )


@receiver(pre_delete, sender=Deploy)
def cleanup_deploy_resources(sender, instance: Deploy, **kwargs):
    """
    On Deploy delete:
      - Remove zip + empty dirs
      - If this deploy is selected by any Service, stop/remove its container
        (and image for app platforms). Volumes stay with the Service —
        they are exclusive and cleaned only when the Service is deleted.
    """
    _cleanup_zip_and_dirs(instance)

    try:
        services = Service.objects.filter(
            selected_deploy=instance
        ).select_related("plan")
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
                    DBDeployer().remove(container_name)
                else:
                    OrchestratorDeploy.remove_all(container_name)
            except Exception:
                logger.exception(
                    "High-level cleanup failed for '%s', falling back to low-level managers",
                    container_name,
                )
                try:
                    container = Container(name=container_name)
                    if container.exists():
                        if container.is_running():
                            container.stop(timeout=10)
                        container.remove()
                    Image.remove_by_name(container_name)
                    Image.remove_by_name(f"{container_name}:latest")
                except Exception:
                    logger.exception(
                        "Fallback cleanup also failed for '%s'", container_name
                    )

            Service.objects.filter(pk=service.pk).update(
                selected_deploy=None,
                selected_deploy_at=None,
            )

    except Exception:
        logger.exception(
            "Unexpected error while cleaning Docker resources for Deploy '%s'",
            instance.name,
        )
