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
from deployments.core.swarm import SwarmRuntime, swarm_enabled

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
        file_path = None

    try:
        name = instance.zip_file.name
        instance.zip_file.delete(save=False)
        logger.info("Removed deploy archive: %s", name)
    except Exception as exc:
        logger.exception("Failed to remove deploy archive for '%s'", instance.name)
        raise RuntimeError(
            f"Failed to remove deployment archive for '{instance.name}'."
        ) from exc
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
    A Deploy is an operation/history record, not runtime ownership.

    Deleting a Deploy removes its source artifact/media and clears the legacy
    selected_deploy compatibility projection. It must never stop an active
    ServiceRevision/Swarm Service.
    """
    _cleanup_zip_and_dirs(instance)
    try:
        from deploy.base_images import release_base_image_leases
        release_base_image_leases(str(instance.pk), remove_if_unretained=False)
    except Exception as exc:
        logger.exception(
            "Failed releasing base-image leases for Deploy '%s'",
            instance.name,
        )
        raise RuntimeError(
            f"Failed to release base-image leases for deployment '{instance.name}'."
        ) from exc
    try:
        Service.objects.filter(selected_deploy=instance).update(
            selected_deploy=None,
            selected_deploy_at=None,
        )
    except Exception:
        logger.exception(
            "Failed clearing legacy selected_deploy projection for Deploy '%s'",
            instance.name,
        )
