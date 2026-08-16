import functools
import logging
import os
import tarfile
import tempfile
from django.db import transaction
from django.http import FileResponse
from ..models import Service, PrivateNetwork, Volume
from deploy.models import Deploy
from django.shortcuts import get_object_or_404
from ..serializers import (
    PrivateNetworkSerializer,
    ServiceSerializer,
    VolumeSerializer,
    GetServiceSerializer,
)
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, authentication_classes, permission_classes, action
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from deployments.celery.tasks import deploy as start_service
from deployments.celery.tasks import stop as stop_service
from deployments.celery.tasks import run_db_deploy  # DB platforms
from core.global_settings.config import SERVICE_STATUS_CHOICES
from core.utils import make_uuid4
from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.manager.container_manager import Container
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound as DockerNotFound


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------
def _user_rules(user) -> list:
    try:
        return list(user.rule.rules or [])
    except Exception:
        return []


def _user_has_rule(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return code in _user_rules(user)


def _can_view_all_services(user) -> bool:
    """Admin panel: list/inspect any user's services."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return _user_has_rule(user, "services.view") or _user_has_rule(user, "services.manage")


def _can_manage_all_services(user) -> bool:
    """Admin panel: mutate any user's services / volumes / networks."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return (
        _user_has_rule(user, "services.manage")
        or _user_has_rule(user, "services.delete")
        or _user_has_rule(user, "volumes.manage")
        or _user_has_rule(user, "networks.manage")
    )


def _can_delete_services(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return _user_has_rule(user, "services.delete") or _user_has_rule(user, "services.manage")


def _service_is_mutable(service) -> tuple:
    """
    Volume attach / detach / mounted-delete is allowed when:
      1. service status is idle (stopped / failed / succeeded / empty — NOT
         running, deploying, queued, stopping, pending)
      2. Docker *container* for this service does not exist (even if exited)

    Image presence alone does NOT block: after a normal stop the image may
    remain, and volume topology changes are still safe without a container.
    Use purge_service_runtime if you also want images removed.

    Returns (ok: bool, reason: str).
    """
    if service is None:
        return True, ""

    status = str(getattr(service, "status", "") or "").lower().strip()
    busy = {
        "queued",
        "deploying",
        "stopping",
        "running",
        "updating...",
        "pending",
    }
    if status in busy:
        return (
            False,
            f"Service is '{status}'. Stop it first, then change volumes.",
        )

    name = service.get_docker_service_name()
    try:
        client = Client()()
        try:
            c = client.containers.get(name)
            state = ""
            try:
                state = (c.attrs or {}).get("State", {}).get("Status", "") or c.status
            except Exception:
                state = getattr(c, "status", "") or ""
            return (
                False,
                f"Container still exists (status={state or 'unknown'}). "
                "Use Danger zone → Remove runtime first, then change volumes.",
            )
        except DockerNotFound:
            pass
        except Exception as exc:
            # Unreachable docker: do NOT block — service is already stopped in DB.
            # Blocking here made detach impossible even with no container.
            logger.warning("container check for %s (non-blocking): %s", name, exc)
    except Exception as exc:
        logger.warning("docker client for mutability check (non-blocking): %s", exc)

    return True, ""



def _docker_volume_exists(volume) -> bool:
    """True if the underlying Docker volume is present."""
    try:
        _get_docker_volume(volume)
        return True
    except DockerNotFound:
        return False
    except Exception as exc:
        logger.warning("docker volume exists check failed for %s: %s", getattr(volume, "name", "?"), exc)
        return False


def _get_service_for_user(request, service_id, *, for_update=False, require_manage=False):
    """
    Resolve a service by id for the *current user only*.

    Used exclusively by user-facing endpoints (start/stop/purge/...).
    Even superusers and staff with admin rules only operate on *their own*
    services here. Cross-user access lives under /admin/services/.
    require_manage is kept for call-site compatibility but ownership is
    always enforced.
    """
    qs = Service.objects.all()
    if for_update:
        qs = qs.select_for_update()
    return qs.get(id=service_id, user=request.user)


def _purge_service_runtime(service) -> dict:
    """Force-stop/remove container and related images. Always best-effort."""
    name = service.get_docker_service_name()
    report = {"container": None, "images": [], "errors": []}
    try:
        client = Client()()
    except Exception as exc:
        report["errors"].append(str(exc))
        return report

    # Container
    try:
        c = client.containers.get(name)
        try:
            c.reload()
            if getattr(c, "status", "") == "running":
                c.stop(timeout=15)
        except Exception as e:
            report["errors"].append(f"stop: {e}")
        try:
            c.remove(force=True)
            report["container"] = "removed"
        except Exception as e:
            report["errors"].append(f"remove container: {e}")
            report["container"] = "failed"
    except DockerNotFound:
        report["container"] = "absent"
    except Exception as e:
        report["errors"].append(f"container: {e}")
        report["container"] = "error"

    # Images by reference name
    for ref in (name, f"{name}:latest"):
        try:
            client.images.remove(ref, force=True)
            report["images"].append({"ref": ref, "result": "removed"})
        except Exception as e:
            msg = str(e).lower()
            if "no such image" in msg or "not found" in msg:
                report["images"].append({"ref": ref, "result": "absent"})
            else:
                report["images"].append({"ref": ref, "result": f"error: {e}"})
                report["errors"].append(f"image {ref}: {e}")

    # Update service status if needed
    try:
        from core.global_settings.config import SERVICE_STATUS_CHOICES as SSC

        Service.objects.filter(pk=service.pk).update(status=SSC.STOPPED)
    except Exception:
        try:
            Service.objects.filter(pk=service.pk).update(status="stopped")
        except Exception:
            pass

    return report




def _parse_deploy_config(raw) -> dict:
    """Normalize Deploy.config whether stored as dict or JSON string."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except Exception:
            pass
    return {}


def _resolve_platform(deploy) -> str:
    """config.platform → service.plan.platform → docker."""
    cfg = _parse_deploy_config(getattr(deploy, "config", None))
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    service = getattr(deploy, "service", None)
    plan = getattr(service, "plan", None) if service is not None else None
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    if service is not None and getattr(service, "plan_id", None):
        try:
            from plans.models import Plan

            plat = (
                Plan.objects.filter(pk=service.plan_id)
                .values_list("platform", flat=True)
                .first()
            )
            if plat:
                return str(plat).strip().lower()
        except Exception:
            logger.exception("Failed to resolve plan.platform")
    return "docker"


class ServiceAdminPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


