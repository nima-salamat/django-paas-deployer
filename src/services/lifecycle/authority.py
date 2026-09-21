"""Authoritative activation pointer helpers.

``Service.active_revision`` is the sole runtime authority.
``Service.selected_deploy`` is a write-through compatibility projection only.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from services.models import Service, ServiceRevision
    from deploy.models import Deploy

logger = logging.getLogger(__name__)


def get_authoritative_revision(service: "Service", *, for_update: bool = False) -> Optional["ServiceRevision"]:
    """
    Return the runtime-authoritative revision for *service*.

    Does **not** promote selected_deploy into active_revision. Callers that
    need a one-time migration bridge should use
    ``services.revisioning.get_active_revision`` which may still perform a
    controlled one-way backfill when active_revision is null.
    """
    from services.models import ServiceRevision

    qs = ServiceRevision.objects.select_related("source_deploy")
    if for_update:
        qs = qs.select_for_update()
    revision_id = getattr(service, "active_revision_id", None)
    if not revision_id:
        return None
    return qs.filter(service_id=service.pk, pk=revision_id).first()


def get_authoritative_deploy(service: "Service", *, for_update: bool = False) -> Optional["Deploy"]:
    """
    Resolve the deployment associated with the authoritative active revision.

    Prefer the revision's source_deploy, then the newest Deploy that references
    the revision. Never falls back to selected_deploy as an independent authority.
    """
    revision = get_authoritative_revision(service, for_update=for_update)
    if revision is None:
        return None
    if getattr(revision, "source_deploy_id", None):
        deploy = getattr(revision, "source_deploy", None)
        if deploy is not None:
            return deploy
        from deploy.models import Deploy
        return Deploy.objects.filter(pk=revision.source_deploy_id).first()
    from deploy.models import Deploy
    qs = Deploy.objects.filter(service_id=service.pk, revision_id=revision.pk)
    if for_update:
        qs = qs.select_for_update()
    return qs.order_by("-created_at").first()


def project_selected_deploy_from_revision(revision: "ServiceRevision") -> Optional["Deploy"]:
    """Derive the compatibility selected_deploy value from a revision."""
    if revision is None:
        return None
    if getattr(revision, "source_deploy_id", None):
        return getattr(revision, "source_deploy", None) or None
    from deploy.models import Deploy
    return (
        Deploy.objects.filter(service_id=revision.service_id, revision_id=revision.pk)
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def sync_selected_deploy_projection(service_id, revision: "ServiceRevision | None" = None) -> None:
    """
    Write-through selected_deploy from the authoritative revision.

    Safe to call after activate_revision_locked. Never reads selected_deploy
    as input — only writes the projection.
    """
    from services.models import Service
    from django.utils import timezone

    service = Service.objects.select_for_update().filter(pk=service_id).first()
    if service is None:
        return

    if revision is None:
        revision = get_authoritative_revision(service, for_update=True)

    deploy = project_selected_deploy_from_revision(revision) if revision else None
    deploy_id = getattr(deploy, "pk", None)
    Service.objects.filter(pk=service_id).update(
        selected_deploy_id=deploy_id,
        selected_deploy_at=timezone.now() if deploy_id else None,
    )
    logger.debug(
        "sync_selected_deploy_projection service=%s deploy=%s revision=%s",
        service_id, deploy_id, getattr(revision, "pk", None),
    )
