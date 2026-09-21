"""Service-centric revision helpers.

A Service owns its desired configuration. A Revision is the immutable snapshot
that a Deployment executes. Legacy Deploy rows remain supported while the
runtime migrates away from using Deploy.config as the source of truth.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import transaction
from django.utils import timezone

from services.models import Service, ServiceProcess, ServiceRevision


_SENSITIVE_KEY_TOKENS = (
    "password",
    "secret",
    "token",
    "private_key",
    "api_key",
    "apikey",
    "signing_key",
)


def _is_sensitive_key(key: object) -> bool:
    lowered = str(key).strip().lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def redact_config(value: Any) -> tuple[Any, list[str]]:
    """Return a recursively redacted copy and the keys that were redacted."""
    secret_keys: list[str] = []

    def walk(node: Any, path: str = "") -> Any:
        if isinstance(node, dict):
            output = {}
            for key, item in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if _is_sensitive_key(key):
                    output[key] = "[REDACTED]"
                    secret_keys.append(key_path)
                else:
                    output[key] = walk(item, key_path)
            return output
        if isinstance(node, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return deepcopy(node)

    return walk(value or {}), sorted(set(secret_keys))


def _normalize_process_specs(service: Service, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize explicit process config, with a safe legacy fallback."""
    raw = config.get("processes")

    if isinstance(raw, dict):
        raw = [
            {"name": name, **(value if isinstance(value, dict) else {"command": value})}
            for name, value in raw.items()
        ]

    if isinstance(raw, list):
        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("type") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "name": name[:64],
                    "process_type": str(item.get("process_type") or item.get("type") or "custom")[:32],
                    "command": item.get("command"),
                    "entrypoint": item.get("entrypoint"),
                    "replicas": max(1, int(item.get("replicas") or 1)),
                    "enabled": bool(item.get("enabled", True)),
                    "environment": dict(item.get("environment") or {}),
                    "healthcheck": dict(item.get("healthcheck") or {}),
                    "resources": dict(item.get("resources") or {}),
                    "metadata": dict(item.get("metadata") or {}),
                }
            )
        if normalized:
            return normalized

    existing = list(
        ServiceProcess.objects.filter(service=service).order_by("created_at", "name")
    )
    if existing:
        return [process.to_snapshot() for process in existing]

    fallback = [
        {
            "name": "web",
            "process_type": "web",
            "command": config.get("start_command"),
            "entrypoint": config.get("entry_point"),
            "replicas": max(1, int(config.get("worker_count") or 1)),
            "enabled": True,
            "environment": {},
            "healthcheck": {},
            "resources": dict(config.get("resource_limits") or {}),
            "metadata": {},
        }
    ]

    if bool(config.get("celery")):
        fallback.append(
            {
                "name": "worker",
                "process_type": "worker",
                "command": config.get("worker_command") or "celery -A $CELERY_APP worker",
                "entrypoint": None,
                "replicas": max(1, int(config.get("worker_count") or 1)),
                "enabled": True,
                "environment": {},
                "healthcheck": {},
                "resources": dict(config.get("resource_limits") or {}),
                "metadata": {"derived_from_legacy_celery": True},
            }
        )
        if bool(config.get("celery_beat")):
            fallback.append(
                {
                    "name": "scheduler",
                    "process_type": "scheduler",
                    "command": config.get("scheduler_command")
                    or "celery -A $CELERY_APP beat",
                    "entrypoint": None,
                    "replicas": 1,
                    "enabled": True,
                    "environment": {},
                    "healthcheck": {},
                    "resources": {},
                    "metadata": {"derived_from_legacy_celery_beat": True},
                }
            )

    return fallback


def _sync_processes(service: Service, specs: list[dict[str, Any]]) -> None:
    """Bring the mutable ServiceProcess layer in line with explicit specs."""
    for spec in specs:
        ServiceProcess.objects.update_or_create(
            service=service,
            name=spec["name"],
            defaults={
                "process_type": spec["process_type"],
                "command": spec.get("command"),
                "entrypoint": spec.get("entrypoint"),
                "replicas": spec.get("replicas", 1),
                "enabled": spec.get("enabled", True),
                "environment": spec.get("environment") or {},
                "healthcheck": spec.get("healthcheck") or {},
                "resources": spec.get("resources") or {},
                "metadata": spec.get("metadata") or {},
            },
        )


@transaction.atomic
def ensure_revision_for_deploy(deploy, *, force_new: bool = False):
    """Create or reuse the immutable revision targeted by a Deploy."""
    from deploy.models import Deploy

    deploy = (
        Deploy.objects.select_for_update()
        .select_related("service", "created_by")
        .get(pk=deploy.pk)
    )

    if deploy.revision_id and not force_new:
        return deploy

    service = Service.objects.select_for_update().get(pk=deploy.service_id)
    config = deepcopy(deploy.config) if isinstance(deploy.config, dict) else {}

    snapshot, secret_keys = redact_config(config)
    process_specs = _normalize_process_specs(service, config)
    _sync_processes(service, process_specs)

    previous = (
        ServiceRevision.objects.filter(service=service)
        .order_by("-revision_number")
        .first()
    )
    next_number = (previous.revision_number if previous else 0) + 1

    revision = ServiceRevision.objects.create(
        service=service,
        revision_number=next_number,
        source_deploy=deploy,
        state=ServiceRevision.State.CREATED,
        config_snapshot=snapshot if isinstance(snapshot, dict) else {},
        process_snapshot=process_specs,
        secret_keys=secret_keys,
        created_by=deploy.created_by,
    )

    Deploy.objects.filter(pk=deploy.pk).update(revision=revision)
    deploy.revision = revision
    return deploy


@transaction.atomic
def activate_revision_locked(service: Service, revision_id) -> ServiceRevision:
    """Activate a revision while the caller already holds the service lock."""
    revision = (
        ServiceRevision.objects.select_for_update()
        .filter(pk=revision_id, service_id=service.pk)
        .first()
    )
    if revision is None:
        raise ValueError("Deployment references a revision that does not belong to this service.")

    ServiceRevision.objects.filter(
        service=service,
        state=ServiceRevision.State.ACTIVE,
    ).exclude(pk=revision.pk).update(
        state=ServiceRevision.State.SUPERSEDED,
    )

    revision.state = ServiceRevision.State.ACTIVE
    revision.activated_at = timezone.now()
    revision.save(update_fields=["state", "activated_at", "updated_at"])

    Service.objects.filter(pk=service.pk).update(active_revision=revision)
    service.active_revision = revision
    return revision
