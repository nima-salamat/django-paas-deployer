"""Tenant-aware application image retention and global BuildKit cache governance.

Docker/BuildKit owns physical shared cache. PassDeployer owns logical records
for application images so user/service quotas can be enforced without claiming
that shared BuildKit blobs are privately owned by a tenant.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import logging
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from deploy.models import (
    BaseRuntimeImage,
    BuildCacheArtifact,
    BuildCacheQuota,
    Deploy,
    DeploymentStatusChoices,
)
from deployments.core.manager.client_manager import get_docker_client

logger = logging.getLogger(__name__)
_MB = 1024 * 1024


def build_cache_policy() -> dict[str, int | bool]:
    try:
        from core.settings_service import (
            build_cache_batch_size,
            build_cache_cleanup_target_percent,
            build_cache_enabled,
            build_cache_global_limit_mb,
            build_cache_keep_successful_deployments,
            build_cache_retention_days,
            build_cache_service_quota_mb,
            build_cache_user_quota_mb,
        )
        return {
            "enabled": build_cache_enabled(),
            "global_limit_mb": build_cache_global_limit_mb(),
            "user_quota_mb": build_cache_user_quota_mb(),
            "service_quota_mb": build_cache_service_quota_mb(),
            "retention_days": build_cache_retention_days(),
            "keep_successful_deployments": build_cache_keep_successful_deployments(),
            "cleanup_target_percent": build_cache_cleanup_target_percent(),
            "batch_size": build_cache_batch_size(),
        }
    except Exception:
        return {
            "enabled": True,
            "global_limit_mb": 20480,
            "user_quota_mb": 5120,
            "service_quota_mb": 2048,
            "retention_days": 30,
            "keep_successful_deployments": 3,
            "cleanup_target_percent": 80,
            "batch_size": 50,
        }


def get_global_build_cache_usage(client=None) -> dict[str, int]:
    try:
        client = client or get_docker_client()
        data = client.api.df() or {}
        usage = data.get("BuildCacheUsage") or data.get("BuildCache") or {}
        if not isinstance(usage, dict):
            usage = {}
        return {
            "total_size": int(usage.get("TotalSize") or usage.get("Size") or 0),
            "reclaimable": int(usage.get("Reclaimable") or 0),
            "active_count": int(usage.get("ActiveCount") or 0),
            "total_count": int(usage.get("TotalCount") or 0),
        }
    except Exception as exc:
        logger.warning("Unable to inspect Docker build cache usage: %s", exc)
        return {
            "total_size": 0,
            "reclaimable": 0,
            "active_count": 0,
            "total_count": 0,
            "error": str(exc),
        }


def prune_global_build_cache(*, force: bool = False, client=None) -> dict[str, Any]:
    """Apply global BuildKit age cleanup and a hard storage target."""
    policy = build_cache_policy()
    if not policy["enabled"] and not force:
        return {"status": "disabled", "deleted": 0, "reclaimed_bytes": 0}

    client = client or get_docker_client()
    before = get_global_build_cache_usage(client)
    limit_bytes = int(policy["global_limit_mb"]) * _MB
    target_percent = max(50, min(95, int(policy["cleanup_target_percent"])))
    target_bytes = int(limit_bytes * target_percent / 100)
    retention_days = int(policy["retention_days"])
    reclaimed = deleted = calls = 0

    try:
        # TTL cleanup works independently from the size ceiling.
        if retention_days > 0:
            result = client.api.prune_builds(
                filters={"until": f"{retention_days}d"},
                all=False,
            ) or {}
            calls += 1
            deleted += len(result.get("CachesDeleted") or [])
            reclaimed += int(result.get("SpaceReclaimed") or 0)

        usage = get_global_build_cache_usage(client)
        if force or int(usage["total_size"]) > limit_bytes:
            result = client.api.prune_builds(
                filters=None,
                keep_storage=target_bytes,
                all=False,
            ) or {}
            calls += 1
            deleted += len(result.get("CachesDeleted") or [])
            reclaimed += int(result.get("SpaceReclaimed") or 0)

        after = get_global_build_cache_usage(client)
        return {
            "status": "cleaned" if calls else "healthy",
            "before": before,
            "after": after,
            "deleted": deleted,
            "reclaimed_bytes": reclaimed,
            "calls": calls,
            "limit_bytes": limit_bytes,
            "target_bytes": target_bytes,
        }
    except Exception as exc:
        logger.exception("Global Docker build cache pruning failed")
        return {
            "status": "error",
            "before": before,
            "after": get_global_build_cache_usage(client),
            "deleted": deleted,
            "reclaimed_bytes": reclaimed,
            "calls": calls,
            "error": str(exc),
        }


def _effective_service_quota(service_id: str) -> dict[str, int]:
    policy = build_cache_policy()
    user_id = (
        BuildCacheArtifact.objects.filter(service_id=service_id)
        .values_list("user_id", flat=True)
        .first()
    )
    service_override = BuildCacheQuota.objects.filter(service_id=service_id).first()
    user_override = BuildCacheQuota.objects.filter(user_id=user_id).first() if user_id else None

    def choose(name: str, default: int) -> int:
        if service_override is not None and getattr(service_override, name, None) is not None:
            return int(getattr(service_override, name))
        if user_override is not None and getattr(user_override, name, None) is not None:
            return int(getattr(user_override, name))
        return int(default)

    return {
        "quota_mb": choose("quota_mb", int(policy["service_quota_mb"])),
        "retention_days": choose("retention_days", int(policy["retention_days"])),
        "keep_successful_deployments": choose(
            "keep_successful_deployments",
            int(policy["keep_successful_deployments"]),
        ),
    }


def _effective_user_quota(user_id: str) -> dict[str, int]:
    policy = build_cache_policy()
    override = BuildCacheQuota.objects.filter(user_id=user_id).first()

    def choose(name: str, default: int) -> int:
        if override is not None and getattr(override, name, None) is not None:
            return int(getattr(override, name))
        return int(default)

    return {
        "quota_mb": choose("quota_mb", int(policy["user_quota_mb"])),
        "retention_days": choose("retention_days", int(policy["retention_days"])),
        "keep_successful_deployments": choose(
            "keep_successful_deployments",
            int(policy["keep_successful_deployments"]),
        ),
    }


def _artifact_rows(*, service_id=None, user_id=None):
    qs = BuildCacheArtifact.objects.filter(reclaimed_at__isnull=True)
    if service_id is not None:
        qs = qs.filter(service_id=service_id)
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    return list(qs.order_by("last_used_at", "created_at"))


def _unique_usage(rows) -> tuple[int, dict[str, int]]:
    sizes: dict[str, int] = {}
    for row in rows:
        key = str(row.image_id or row.image_ref)
        sizes[key] = max(sizes.get(key, 0), int(row.size_bytes or 0))
    return sum(sizes.values()), sizes


def _protected_deployments(service_id: str, keep_successful: int) -> set[str]:
    state = (
        BuildCacheArtifact.objects.filter(service_id=service_id)
        .values("service__active_revision_id", "service__selected_deploy_id")
        .first()
    )
    protected: set[str] = set()
    if state:
        selected = state.get("service__selected_deploy_id")
        if selected:
            protected.add(str(selected))
        active_revision = state.get("service__active_revision_id")
    else:
        active_revision = None

    if active_revision:
        protected.update(
            str(pk) for pk in Deploy.objects.filter(
                service_id=service_id,
                revision_id=active_revision,
            ).values_list("pk", flat=True)
        )

    protected.update(
        str(pk) for pk in Deploy.objects.filter(
            service_id=service_id,
            status__in=[
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
                DeploymentStatusChoices.ROLLING_BACK,
            ],
        ).values_list("pk", flat=True)
    )

    if keep_successful > 0:
        protected.update(
            str(pk) for pk in Deploy.objects.filter(
                service_id=service_id,
                status=DeploymentStatusChoices.SUCCEEDED,
            ).order_by("-created_at", "-pk").values_list("pk", flat=True)[:keep_successful]
        )
    return protected


def _running_image_ids(client=None) -> set[str]:
    client = client or get_docker_client()
    ids: set[str] = set()
    try:
        for container in client.containers.list(all=True):
            image_id = str(getattr(getattr(container, "image", None), "id", "") or "")
            if image_id:
                ids.add(image_id)
    except Exception:
        logger.debug("Unable to enumerate local containers for cache protection", exc_info=True)
    return ids


def _base_image_ids() -> set[str]:
    return {
        str(value)
        for value in BaseRuntimeImage.objects.exclude(image_id="")
        .values_list("image_id", flat=True)
        if value
    }


def _remove_image_group(
    image_id: str,
    rows: list[BuildCacheArtifact],
    *,
    client=None,
) -> tuple[bool, str, int]:
    client = client or get_docker_client()
    size = max((int(row.size_bytes or 0) for row in rows), default=0)
    if not image_id:
        return False, "Application artifact has no Docker image identity.", 0

    try:
        client.images.remove(image_id, force=False)
    except Exception as exc:
        # The Docker image may have been removed independently; the DB record
        # should converge to reclaimed instead of retrying forever.
        if type(exc).__name__ == "ImageNotFound":
            return True, "", size
        return False, str(exc), 0

    try:
        client.images.get(image_id)
    except Exception:
        return True, "", size
    return False, "Docker image still exists after non-force removal.", 0


def _mark_group_reclaimed(rows: list[BuildCacheArtifact], error: str = "") -> None:
    now = timezone.now()
    for row in rows:
        row.reclaimed_at = now if not error else None
        row.reclaim_error = error[:4000]
        row.save(update_fields=["reclaimed_at", "reclaim_error", "updated_at"])


def _cleanup_rows(
    rows,
    *,
    protected_deployments: set[str],
    cutoff,
    quota_bytes: int,
    current_usage: int,
    client=None,
    batch_size: int = 50,
) -> dict[str, int]:
    client = client or get_docker_client()
    running_ids = _running_image_ids(client)
    protected_image_ids = _base_image_ids()
    # Any protected/pinned artifact protects the underlying image identity as
    # a whole. This avoids deleting an image through an unprotected duplicate
    # record that happens to share the same Docker image ID.
    for row in rows:
        image_id = str(row.image_id or "")
        if image_id and (str(row.deployment_id) in protected_deployments or row.pinned):
            protected_image_ids.add(image_id)

    grouped: dict[str, list[BuildCacheArtifact]] = defaultdict(list)
    for row in rows:
        image_id = str(row.image_id or "")
        if image_id in protected_image_ids or image_id in running_ids:
            continue
        if not image_id:
            row.reclaim_error = "Application cache artifact has no Docker image ID."
            row.save(update_fields=["reclaim_error", "updated_at"])
            continue
        grouped[image_id].append(row)

    removed = reclaimed = failed = 0
    for image_id, group in list(grouped.items())[: max(1, int(batch_size))]:
        oldest = min(
            (r.last_used_at or r.created_at for r in group),
            default=timezone.now(),
        )
        if current_usage <= quota_bytes and oldest > cutoff:
            continue
        ok, error, size = _remove_image_group(image_id, group, client=client)
        if ok:
            _mark_group_reclaimed(group)
            current_usage = max(0, current_usage - size)
            removed += len(group)
            reclaimed += size
        else:
            for row in group:
                row.reclaim_error = error[:4000]
                row.save(update_fields=["reclaim_error", "updated_at"])
            failed += len(group)
    return {"removed": removed, "reclaimed_bytes": reclaimed, "failed": failed}


def enforce_service_cache_quota(service_id: str, *, client=None, batch_size: int | None = None) -> dict[str, Any]:
    policy = build_cache_policy()
    if not policy["enabled"]:
        return {"status": "disabled", "service_id": str(service_id), "removed": 0, "reclaimed_bytes": 0}
    quota = _effective_service_quota(service_id)
    rows = _artifact_rows(service_id=service_id)
    usage, _ = _unique_usage(rows)
    protected = _protected_deployments(service_id, int(quota["keep_successful_deployments"]))
    cutoff = timezone.now() - timedelta(days=max(1, int(quota["retention_days"])))
    result = _cleanup_rows(
        rows,
        protected_deployments=protected,
        cutoff=cutoff,
        quota_bytes=int(quota["quota_mb"]) * _MB,
        current_usage=usage,
        client=client,
        batch_size=batch_size or int(policy["batch_size"]),
    )
    result.update({
        "service_id": str(service_id),
        "quota_mb": int(quota["quota_mb"]),
        "usage_before_bytes": usage,
        "protected_deployments": len(protected),
    })
    return result


def _protected_user_deployments(user_id: str, keep_successful: int) -> set[str]:
    protected: set[str] = set()
    service_ids = (
        BuildCacheArtifact.objects.filter(user_id=user_id)
        .values_list("service_id", flat=True)
        .distinct()
    )
    for service_id in service_ids:
        protected.update(_protected_deployments(str(service_id), keep_successful))
    return protected


def enforce_user_cache_quota(user_id: str, *, client=None, batch_size: int | None = None) -> dict[str, Any]:
    policy = build_cache_policy()
    if not policy["enabled"]:
        return {"status": "disabled", "user_id": str(user_id), "removed": 0, "reclaimed_bytes": 0}
    quota = _effective_user_quota(user_id)
    rows = _artifact_rows(user_id=user_id)
    usage, _ = _unique_usage(rows)
    protected = _protected_user_deployments(user_id, int(quota["keep_successful_deployments"]))
    cutoff = timezone.now() - timedelta(days=max(1, int(quota["retention_days"])))
    result = _cleanup_rows(
        rows,
        protected_deployments=protected,
        cutoff=cutoff,
        quota_bytes=int(quota["quota_mb"]) * _MB,
        current_usage=usage,
        client=client,
        batch_size=batch_size or int(policy["batch_size"]),
    )
    result.update({
        "user_id": str(user_id),
        "quota_mb": int(quota["quota_mb"]),
        "usage_before_bytes": usage,
        "protected_deployments": len(protected),
    })
    return result


def record_application_image(deployment_id: str, image) -> BuildCacheArtifact:
    deploy = Deploy.objects.select_related("service", "service__user").get(pk=deployment_id)
    attrs = getattr(image, "attrs", {}) or {}
    digests = attrs.get("RepoDigests") or []
    image_id = str(getattr(image, "id", "") or "")
    tags = list(getattr(image, "tags", None) or [])
    ref = str(tags[0]) if tags else ""
    artifact, _ = BuildCacheArtifact.objects.update_or_create(
        deployment=deploy,
        defaults={
            "user": deploy.service.user,
            "service": deploy.service,
            "image_ref": ref,
            "image_id": image_id,
            "image_digest": str(digests[0]) if digests else "",
            "size_bytes": max(0, int(attrs.get("Size") or 0)),
            "last_used_at": timezone.now(),
            "reclaimed_at": None,
            "reclaim_error": "",
        },
    )
    return artifact


def mark_application_image_reclaimed(deployment_id: str | None, *, error: str = "") -> int:
    if not deployment_id:
        return 0
    return int(BuildCacheArtifact.objects.filter(deployment_id=deployment_id).update(
        reclaimed_at=None if error else timezone.now(),
        reclaim_error=(error or "")[:4000],
        updated_at=timezone.now(),
    ) or 0)


def get_build_cache_sources(deployment_id: str | None, limit: int = 3) -> list[str]:
    if not deployment_id:
        return []
    try:
        service_id = Deploy.objects.filter(pk=deployment_id).values_list("service_id", flat=True).first()
        if not service_id:
            return []
        rows = (
            BuildCacheArtifact.objects.filter(
                service_id=service_id,
                reclaimed_at__isnull=True,
            )
            .exclude(deployment_id=deployment_id)
            .order_by("-last_used_at", "-created_at")[: max(1, min(int(limit), 8))]
        )
        client = get_docker_client()
        sources: list[str] = []
        seen: set[str] = set()
        for row in rows:
            ref = str(row.image_ref or "").strip()
            if not ref or ref in seen:
                continue
            try:
                client.images.get(ref)
            except Exception:
                continue
            sources.append(ref)
            seen.add(ref)
            row.last_used_at = timezone.now()
            row.reclaim_error = ""
            row.save(update_fields=["last_used_at", "reclaim_error", "updated_at"])
        return sources
    except Exception:
        logger.debug("Unable to resolve build cache sources for deployment=%s", deployment_id, exc_info=True)
        return []


def cache_overview(*, client=None) -> dict[str, Any]:
    policy = build_cache_policy()
    physical = get_global_build_cache_usage(client)
    artifact_qs = BuildCacheArtifact.objects.filter(reclaimed_at__isnull=True)
    logical = artifact_qs.aggregate(size=Sum("size_bytes"))
    return {
        "enabled": bool(policy["enabled"]),
        "physical": physical,
        "global_limit_bytes": int(policy["global_limit_mb"]) * _MB,
        "target_bytes": int(policy["global_limit_mb"]) * _MB * int(policy["cleanup_target_percent"]) // 100,
        "default_user_quota_mb": int(policy["user_quota_mb"]),
        "default_service_quota_mb": int(policy["service_quota_mb"]),
        "retention_days": int(policy["retention_days"]),
        "keep_successful_deployments": int(policy["keep_successful_deployments"]),
        "logical_artifact_usage_bytes": int(logical.get("size") or 0),
        "artifact_count": int(artifact_qs.count()),
    }
