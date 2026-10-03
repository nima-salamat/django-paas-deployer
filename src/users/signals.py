import logging
import os
import shutil

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from users.models import User, Profile
from services.models import Service

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
    """
    Full cleanup when a user is deleted:
      - Stop/remove all service containers (and images for app plans)
      - Remove all Docker volumes owned by the user (exclusive model)
      - Remove all Docker private networks
      - Delete profile images + deployment media directory
    """
    user_id = instance.id
    logger.info(
        "=== pre_delete User %s (id=%s) → full cleanup started ===",
        instance,
        user_id,
    )

    from deploy.models import Deploy

    active_deploys = list(
        Deploy.objects.filter(
            service__user_id=instance.pk,
            status__in={"pending", "running", "rolling_back"},
        ).only("pk")
    )
    if active_deploys:
        raise RuntimeError(
            "User deletion is blocked while owned deployments are still active; "
            "request account deletion through the deletion coordinator."
        )

    services = list(Service.objects.filter(user=instance).values_list("pk", flat=True))
    logger.info(
        "User %s owns %s service(s); Service pre_delete handlers own their Swarm/container runtime cleanup.",
        user_id,
        len(services),
    )


    # Volume pre_delete performs the authoritative Docker cleanup for every
    # cascaded Volume row. Do not remove Docker volumes here: swallowing a
    # removal failure before the DB row is cascaded would create invisible
    # physical storage that no longer has a Django owner.
    logger.info(
        "User %s volume cleanup is delegated to Volume.pre_delete so DB rows "
        "are retained if Docker storage cannot be removed.",
        user_id,
    )
    # PrivateNetwork.pre_delete is the authoritative network cleanup path.
    # Delegating to it preserves the same ownership-label and attachment checks
    # used by direct network deletion and avoids deleting an unmanaged network
    # from the User signal.
    logger.info(
        "User %s private-network cleanup is delegated to PrivateNetwork.pre_delete.",
        user_id,
    )

    # Fence every owned Service before the deletion collector reaches it.
    # This invalidates in-flight deployment workers before the Service row is
    # removed and is the project-wide delete intent for lifecycle state.
    for service_id in Service.objects.filter(user_id=user_id).values_list("pk", flat=True).iterator():
        try:
            from services.lifecycle import mark_deleted
            mark_deleted(service_id)
        except Exception:
            logger.exception(
                "Failed to fence Service %s for User %s deletion.",
                service_id,
                user_id,
            )
            raise


    try:
        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root:
            user_deploy_dir = os.path.join(
                media_root, "deployments", str(user_id)
            )
            if os.path.isdir(user_deploy_dir):
                shutil.rmtree(user_deploy_dir, ignore_errors=False)
                if os.path.isdir(user_deploy_dir):
                    raise RuntimeError(
                        f"User deployment directory still exists after cleanup: {user_deploy_dir}"
                    )
                logger.info(
                    "Removed user deployment directory: %s", user_deploy_dir
                )
    except Exception:
        logger.exception(
            "Failed to remove user deployment directory for user_id=%s",
            user_id,
        )
        raise

    logger.info("=== pre_delete User %s finished ===", user_id)


@receiver(pre_delete, sender=Profile)
def cleanup_profile_image(sender, instance: Profile, **kwargs):
    if instance.image:
        name = str(getattr(instance.image, "name", "") or "")
        try:
            instance.image.delete(save=False)
            logger.info("Deleted profile image: %s", name)
        except Exception as exc:
            logger.exception("Failed to delete profile image: %s", name)
            raise RuntimeError(
                f"Failed to remove profile image '{name}'."
            ) from exc
