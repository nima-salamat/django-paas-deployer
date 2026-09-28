"""Base runtime image registry and resolver for application deployments.

Base images contain only operator-owned runtime/tooling layers. Application
sources and tenant dependencies are intentionally never copied into them.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import socket
import tarfile
import time
import uuid
from datetime import timedelta
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import BaseRuntimeImage, BaseRuntimeImageLease
from deployments.core.manager.client_manager import get_docker_client
from deployments.core.manager.image_manager import Image

logger = logging.getLogger(__name__)

_PUBLIC_DEFAULT_DOCKER = "docker.io"


def _docker_mirror() -> str:
    try:
        from core.settings_service import mirror_docker
        value = str(mirror_docker() or "").strip().rstrip("/")
        if value:
            return value
    except Exception:
        pass
    try:
        from core.global_settings.config import MIRROR_DOCKER
        value = str(MIRROR_DOCKER or _PUBLIC_DEFAULT_DOCKER).strip().rstrip("/")
        return value or _PUBLIC_DEFAULT_DOCKER
    except Exception:
        return _PUBLIC_DEFAULT_DOCKER


def _host_key() -> str:
    explicit = os.environ.get("DEPLOY_DOCKER_HOST_ID")
    if explicit:
        return explicit
    try:
        client = get_docker_client()
        info = client.info() or {}
        daemon_id = info.get("ID") or info.get("SystemID") or info.get("Name")
        if daemon_id:
            return str(daemon_id)[:255]
    except Exception:
        pass
    return socket.gethostname()


def _normalize_version(value: Any, default: str) -> str:
    raw = str(value or default).strip().lstrip("vV")
    m = re.search(r"(\d+(?:\.\d+){0,2})", raw)
    if not m:
        return default
    parts = m.group(1).split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else parts[0]


def _tag_token(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip(".-_") or "default"


@dataclass(frozen=True)
class BaseImageSpec:
    logical_runtime: str
    version: str
    variant: str
    source_image: str
    repository: str
    tag: str
    dockerfile: str

    @property
    def image_ref(self) -> str:
        return f"{self.repository}:{self.tag}"


def _spec_fingerprint(spec: BaseImageSpec) -> str:
    payload = "\n".join([
        "base-image-definition-v1",
        spec.logical_runtime,
        spec.version,
        spec.variant,
        spec.source_image,
        spec.repository,
        spec.tag,
        spec.dockerfile,
    ]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def deployment_phase_remaining_seconds(deployment_or_id, *, now=None) -> int | None:
    """Return remaining seconds for the deployment's current lifecycle phase."""
    from core.settings_service import base_image_build_timeout_minutes, deploy_timeout_minutes
    from .models import Deploy
    deploy = deployment_or_id
    if not hasattr(deploy, "lifecycle_phase_deadline"):
        deploy = Deploy.objects.filter(pk=deployment_or_id).first()
    if deploy is None:
        return None
    now = now or timezone.now()
    deadline = deploy.lifecycle_phase_deadline(
        base_timeout_minutes=base_image_build_timeout_minutes(),
        application_timeout_minutes=deploy_timeout_minutes(),
        now=now,
    )
    if deadline is None:
        return None
    return max(0, int((deadline - now).total_seconds()))

def mark_base_image_phase_started(deployment_id: str | None):
    """Start a deployment's dedicated base-image budget without resetting it."""
    if not deployment_id:
        return None
    from .models import Deploy
    now = timezone.now()
    with transaction.atomic():
        deploy = Deploy.objects.select_for_update().filter(pk=deployment_id).first()
        if deploy is None:
            return None
        started = deploy.base_image_wait_started_at or now
        deploy.stage = "base_image"
        deploy.base_image_wait_started_at = started
        deploy.base_image_ready_at = None
        deploy.application_started_at = None
        deploy.status_message = "Waiting for the required base runtime image."
        deploy.save(update_fields=[
            "stage", "base_image_wait_started_at", "base_image_ready_at",
            "application_started_at", "status_message", "updated_at",
        ])
        return started

def mark_application_phase_started(deployment_id: str | None):
    """Start a fresh application timeout after base-image resolution."""
    if not deployment_id:
        return None
    from .models import Deploy
    now = timezone.now()
    with transaction.atomic():
        deploy = Deploy.objects.select_for_update().filter(pk=deployment_id).first()
        if deploy is None:
            return None
        if deploy.base_image_wait_started_at:
            deploy.base_image_ready_at = now
        deploy.application_started_at = now
        if str(deploy.stage or "").strip().lower() == "base_image":
            deploy.stage = "starting"
        deploy.save(update_fields=[
            "base_image_ready_at", "application_started_at", "stage", "updated_at",
        ])
        return now

def _dockerfile_with_fingerprint(spec: BaseImageSpec, fingerprint: str) -> str:
    """Add an inspectable content fingerprint without making it part of itself."""
    match = re.search(r"^FROM[^\n]*$", spec.dockerfile, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        raise ValueError(f"Base image Dockerfile has no FROM instruction: {spec.image_ref}")
    label = (
        f'\nLABEL io.passdeployer.base-definition="{fingerprint}"'
        f' io.passdeployer.base-runtime="{spec.logical_runtime}:{spec.version}:{spec.variant}"'
    )
    return spec.dockerfile[:match.end()] + label + spec.dockerfile[match.end():]


def _legacy_php(version: str, *, public_root: bool) -> BaseImageSpec:
    """Reconstruct an old PHP definition only for in-flight legacy rows."""
    src = f"{_docker_mirror()}/php:{version}-apache"
    variant = "apache-public" if public_root else "apache-root"
    repository = "paas-base/php-apache" if public_root else "paas-base/php-apache-root"
    doc_root = "/var/www/html/public" if public_root else "/var/www/html"
    return BaseImageSpec(
        "php", version, variant, src, repository, f"{_tag_token(version)}-r1",
        f'''FROM {src}

ENV APACHE_DOCUMENT_ROOT={doc_root}\
    COMPOSER_ALLOW_SUPERUSER=1\
    COMPOSER_MEMORY_LIMIT=-1

WORKDIR /var/www/html

RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev \
        libicu-dev libonig-dev libxml2-dev curl ca-certificates \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && missing=""; for ext in mysqli pdo pdo_mysql opcache zip gd intl bcmath mbstring exif pcntl; do \
         if php -m | grep -Eiq "^${{ext}}$"; then \
             echo "PHP extension ${{ext}} already enabled; skipping build"; \
         else missing="$missing $ext"; fi; \
       done; \
       if [ -n "$missing" ]; then docker-php-ext-install -j$(nproc) $missing; fi \
    && a2enmod rewrite headers mime dir expires alias \
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
    && printf '%s\\n' 'ServerName localhost' > /etc/apache2/conf-available/deployer-server-name.conf \
    && a2enconf deployer-server-name \
    && printf '%s\\n' '<VirtualHost *:80>' '    ServerName localhost' '    DocumentRoot {doc_root}' '    <Directory {doc_root}>' '        AllowOverride All' '        Require all granted' '        Options FollowSymLinks' '    </Directory>' '    RewriteEngine On' '    RewriteCond %{{REQUEST_FILENAME}} -f [OR]' '    RewriteCond %{{REQUEST_FILENAME}} -d' '    RewriteRule ^ - [END]' '    RewriteCond %{{REQUEST_FILENAME}} !-f' '    RewriteCond %{{REQUEST_FILENAME}} !-d' '    RewriteRule ^ index.php [L]' '</VirtualHost>' > /etc/apache2/sites-available/000-default.conf \
    && echo 'opcache.enable=1' >> /usr/local/etc/php/conf.d/opcache-laravel.ini \
    && rm -rf /var/lib/apt/lists/*

COPY --from={_docker_mirror()}/composer:2 /usr/bin/composer /usr/bin/composer

CMD ["apache2-foreground"]
'''
    )
def _php(version: str) -> BaseImageSpec:
    """Return the canonical generic PHP/Apache runtime base.

    DocumentRoot is application-specific and is applied later by
    ``DockerfileGenerator``. Therefore PHP has exactly one base identity:
    variant=apache, repository=paas-base/php-apache.
    """
    src = f"{_docker_mirror()}/php:{version}-apache"
    repository = "paas-base/php-apache"
    return BaseImageSpec(
        "php",
        version,
        "apache",
        src,
        repository,
        f"{_tag_token(version)}-r1",
        f'''FROM {src}

ENV COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_MEMORY_LIMIT=-1

WORKDIR /var/www/html

RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev \
        libicu-dev libonig-dev libxml2-dev curl ca-certificates \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && missing=""; for ext in mysqli pdo pdo_mysql opcache zip gd intl bcmath mbstring exif pcntl; do \
         if php -m | grep -Eiq "^${{ext}}$"; then \
             echo "PHP extension ${{ext}} already enabled; skipping build"; \
         else \
             missing="$missing $ext"; \
         fi; \
       done; \
       if [ -n "$missing" ]; then \
         echo "Installing missing PHP extensions:$missing"; \
         docker-php-ext-install -j$(nproc) $missing; \
       else \
         echo "All requested PHP extensions already enabled; skipping docker-php-ext-install"; \
       fi \
    && a2enmod rewrite headers mime dir expires alias \
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
    && printf '%s\\n' 'ServerName localhost' > /etc/apache2/conf-available/deployer-server-name.conf \
    && a2enconf deployer-server-name \
    && echo 'opcache.enable=1' >> /usr/local/etc/php/conf.d/opcache-laravel.ini \
    && rm -rf /var/lib/apt/lists/*

COPY --from={_docker_mirror()}/composer:2 /usr/bin/composer /usr/bin/composer

CMD ["apache2-foreground"]
'''
    )

def _python(version: str) -> BaseImageSpec:
    src = f"{_docker_mirror()}/python:{version}-slim"
    return BaseImageSpec(
        "python", version, "slim", src, "paas-base/python-slim", f"{_tag_token(version)}-r1",
        f'''FROM {src}\nENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1\nWORKDIR /app\nRUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc curl ca-certificates \\\n    && python -m pip install --no-cache-dir --upgrade pip wheel setuptools \\\n    && rm -rf /var/lib/apt/lists/*\nCMD ["python"]\n'''
    )


def _node(version: str) -> BaseImageSpec:
    src = f"{_docker_mirror()}/node:{version}-alpine"
    return BaseImageSpec(
        "node", version, "alpine", src, "paas-base/node-alpine", f"{_tag_token(version)}-r1",
        f'''FROM {src}\nWORKDIR /app\nRUN corepack enable && npm config set fund false && npm config set audit false\nCMD ["node"]\n'''
    )


def _nginx(version: str) -> BaseImageSpec:
    src = f"{_docker_mirror()}/nginx:{version}"
    return BaseImageSpec(
        "nginx", version, "alpine", src, "paas-base/nginx", f"{_tag_token(version)}-r1",
        f'''FROM {src}\nEXPOSE 80\nCMD ["nginx", "-g", "daemon off;"]\n'''
    )


def _go(version: str) -> BaseImageSpec:
    src = f"{_docker_mirror()}/golang:{version}-alpine"
    return BaseImageSpec(
        "go", version, "alpine", src, "paas-base/go-alpine", f"{_tag_token(version)}-r1",
        f'''FROM {src}\nRUN apk add --no-cache git ca-certificates\nWORKDIR /app\nENV CGO_ENABLED=0\nCMD ["go", "version"]\n'''
    )


def make_specs(config) -> list[BaseImageSpec]:
    platform = str(getattr(config, "platform", "") or "").lower().strip()
    runtime = str(getattr(config, "runtime_version", "") or "").strip()
    specs: list[BaseImageSpec] = []
    if platform in {"php", "laravel", "lumen", "symfony", "codeigniter"}:
        version = _normalize_version(runtime, "8.4")
        specs.append(_php(version))
        if platform == "laravel" and getattr(config, "frontend_root", None) is not None:
            specs.append(_node("20"))
    elif platform in {"python", "django", "flask", "fastapi"}:
        specs.append(_python(_normalize_version(runtime, "3.11")))
    elif platform in {"nodejs", "nextjs", "react", "vuejs", "vue", "angular", "vite", "express"}:
        specs.append(_node(_normalize_version(runtime, "20")))
        if platform in {"react", "vuejs", "vue", "angular", "vite"}:
            specs.append(_nginx("alpine"))
    elif platform == "static":
        specs.append(_nginx("alpine"))
    elif platform == "go":
        specs.append(_go(_normalize_version(runtime, "1.21")))
    return specs

def _core_settings():
    try:
        from core.models import CoreSettings
        return CoreSettings.load()
    except Exception:
        return None


def base_image_settings() -> dict[str, bool]:
    try:
        from core.settings_service import (
            base_images_auto_build,
            base_images_auto_register_existing,
            base_images_enabled,
            base_images_retain_after_deploy,
        )
        return {
            "enabled": base_images_enabled(),
            "auto_build": base_images_auto_build(),
            "retain_after_deploy": base_images_retain_after_deploy(),
            "auto_register_existing": base_images_auto_register_existing(),
        }
    except Exception:
        return {
            "enabled": True,
            "auto_build": True,
            "retain_after_deploy": True,
            "auto_register_existing": True,
        }


def _docker_image_exists(ref: str) -> bool:
    client = get_docker_client()
    try:
        client.images.get(ref)
        return True
    except Exception:
        return False


def _tar_for_dockerfile(text: str) -> io.BytesIO:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        payload = text.encode("utf-8")
        info = tarfile.TarInfo("Dockerfile")
        info.size = len(payload)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(payload))
    stream.seek(0)
    return stream


def _build_spec(
    spec: BaseImageSpec,
    *,
    build_policy: dict[str, Any] | None = None,
    force_rebuild: bool = False,
    on_output=None,
    ownership_check=None,
    timeout_seconds: float | None = None,
):
    from deployments.common.resource_policy import resolve_build_policy

    effective_policy = resolve_build_policy(build_policy)
    logger.info("Building base runtime image %s from %s", spec.image_ref, spec.source_image)
    fingerprint = _spec_fingerprint(spec)
    image = Image(
        spec.repository,
        spec.tag,
        _dockerfile_with_fingerprint(spec, fingerprint),
        _tar_for_dockerfile(_dockerfile_with_fingerprint(spec, fingerprint)),
        build_resource_policy=effective_policy,
        build_resource_policy_source="server_owned_base_image",
        build_scope="base_image",
        build_options={"pull": True, "no_cache": bool(force_rebuild)},
        deployment_id=f"base:{spec.image_ref}",
    )
    return image.create(
        on_build_output=on_output,
        ownership_check=ownership_check,
        timeout_seconds=timeout_seconds,
    )

def _spec_for_record(row: BaseRuntimeImage) -> BaseImageSpec:
    runtime = str(row.logical_runtime or "").lower()
    version = str(row.runtime_version or "")
    variant = str(row.variant or "default")
    if runtime == "php":
        if variant == "apache":
            return _php(version)
        if variant == "apache-root":
            return _legacy_php(version, public_root=False)
        if variant == "apache-public":
            return _legacy_php(version, public_root=True)
        raise ValueError(f"Unsupported PHP base-image variant '{variant}'")
    if runtime == "python":
        return _python(version)
    if runtime == "node":
        return _node(version)
    if runtime == "nginx":
        return _nginx(version)
    if runtime == "go":
        return _go(version)
    raise ValueError(f"Unsupported base runtime '{runtime}'")


def _local_image_matches_fingerprint(image_ref: str, fingerprint: str) -> bool:
    """Return true only when the local image carries the expected definition label."""
    if not _docker_image_exists(image_ref):
        return False
    try:
        image = get_docker_client().images.get(image_ref)
        labels = ((getattr(image, "attrs", {}) or {}).get("Config") or {}).get("Labels") or {}
        return labels.get("io.passdeployer.base-definition") == fingerprint
    except Exception:
        return False


def _can_use_compatible_local_base_image(
    row: BaseRuntimeImage,
    fingerprint: str,
    *,
    local_exists: bool,
    local_compatible: bool,
) -> bool:
    """Allow a valid local base image even while a same-definition renewal is pending.

    ``BUILDING`` and ``rebuild_requested`` describe the registry lifecycle, not
    the usability of an already-built image. A service deployment may safely use
    the local image when its operator definition fingerprint matches. An active
    renewal can continue in the background, while stale/gapped worker state no
    longer blocks unrelated application deployments.
    """
    return bool(
        local_exists
        and local_compatible
        and row.definition_fingerprint == fingerprint
    )


def request_base_runtime_image_build(
    base_image_id,
    *,
    force_rebuild: bool = False,
    deployment_id: str | None = None,
) -> dict[str, Any]:
    """Queue a base-image build through the canonical Celery lifecycle.

    This is the single operator/manual request path. It never calls Docker
    build from HTTP and never replaces an active owner.
    """
    from deployments.celery.tasks import build_base_runtime_image
    from deployments.common.resource_policy import resolve_build_policy

    with transaction.atomic():
        row = BaseRuntimeImage.objects.select_for_update().get(pk=base_image_id)
        if not row.enabled:
            raise RuntimeError(
                f"Base runtime image {row.logical_runtime}:{row.runtime_version}:{row.variant} is disabled."
            )
        # Legacy PHP rows are compatibility records. Prefer the canonical
        # apache row when one exists; otherwise safely normalize an inactive
        # legacy row before queuing a new canonical build.
        if str(row.logical_runtime).lower() == "php" and row.variant in {"apache-root", "apache-public"}:
            canonical = (
                BaseRuntimeImage.objects.select_for_update()
                .filter(
                    logical_runtime="php",
                    runtime_version=row.runtime_version,
                    variant="apache",
                    architecture=row.architecture,
                    docker_host=row.docker_host,
                )
                .first()
            )
            active_leases = row.leases.filter(released_at__isnull=True).exists()
            if canonical is not None and canonical.pk != row.pk:
                if row.status == BaseRuntimeImage.Status.BUILDING or row.build_task_id or active_leases:
                    if force_rebuild:
                        canonical.rebuild_requested = True
                        canonical.rebuild_requested_at = timezone.now()
                        canonical.save(update_fields=["rebuild_requested", "rebuild_requested_at", "updated_at"])
                    return {
                        "queued": False,
                        "coalesced": True,
                        "waiting": row.status == BaseRuntimeImage.Status.BUILDING,
                        "task_id": canonical.build_task_id,
                        "rebuild_requested": bool(canonical.rebuild_requested),
                        "image_ref": canonical.image_ref,
                    }
                row.status = BaseRuntimeImage.Status.DISABLED
                row.enabled = False
                row.rebuild_requested = False
                row.last_error = f"Legacy PHP identity superseded by {canonical.image_ref}."
                row.last_error_details = {
                    "stage": "base_image",
                    "superseded_by": canonical.image_ref,
                    "legacy_image_ref": row.image_ref,
                    "safe_to_remove_after_release": True,
                }
                row.save(update_fields=[
                    "status", "enabled", "rebuild_requested", "last_error",
                    "last_error_details", "updated_at",
                ])
                row = canonical
            elif not active_leases and row.status != BaseRuntimeImage.Status.BUILDING and not row.build_task_id:
                row.variant = "apache"
                spec = _php(str(row.runtime_version))
                row.source_image = spec.source_image
                row.image_repository = spec.repository
                row.image_tag = spec.tag
                row.image_ref = spec.image_ref
                row.definition_fingerprint = ""
                row.status = BaseRuntimeImage.Status.PENDING
                row.image_id = ""
                row.image_digest = ""
                row.save(update_fields=[
                    "variant", "source_image", "image_repository", "image_tag",
                    "image_ref", "definition_fingerprint", "status", "image_id",
                    "image_digest", "updated_at",
                ])

        spec = _spec_for_record(row)
        fingerprint = _spec_fingerprint(spec)
        if row.status == BaseRuntimeImage.Status.BUILDING:
            if force_rebuild and not row.rebuild_requested:
                row.rebuild_requested = True
                row.rebuild_requested_at = timezone.now()
                row.save(update_fields=["rebuild_requested", "rebuild_requested_at", "updated_at"])
            return {
                "queued": False, "coalesced": True, "waiting": True,
                "task_id": row.build_task_id,
                "rebuild_requested": bool(row.rebuild_requested),
                "image_ref": row.image_ref,
            }
        if (
            not force_rebuild
            and not row.rebuild_requested
            and row.definition_fingerprint == fingerprint
            and _local_image_matches_fingerprint(row.image_ref, fingerprint)
        ):
            if row.status != BaseRuntimeImage.Status.READY:
                _mark_local_image_ready(row, expected_fingerprint=fingerprint)
            return {
                "queued": False, "cache_hit": True, "waiting": False,
                "task_id": "", "image_ref": row.image_ref,
            }

        task_id = f"base-image-{row.pk}-{uuid.uuid4()}"
        requested_force = bool(force_rebuild or row.rebuild_requested)
        row.status = BaseRuntimeImage.Status.BUILDING
        row.build_task_id = task_id
        row.build_owner_deployment_id = str(deployment_id or "")[:255]
        row.definition_fingerprint = fingerprint
        row.rebuild_requested = False
        row.rebuild_requested_at = None
        row.build_started_at = timezone.now()
        row.build_completed_at = None
        row.last_error = ""
        row.last_error_details = {}
        row.save(update_fields=[
            "status", "build_task_id", "build_owner_deployment_id",
            "definition_fingerprint", "rebuild_requested", "rebuild_requested_at",
            "build_started_at", "build_completed_at", "last_error",
            "last_error_details", "updated_at",
        ])
    try:
        effective_policy = resolve_build_policy(None)
        build_base_runtime_image.apply_async(
            args=[str(row.pk)],
            kwargs={"force_rebuild": requested_force, "build_policy": effective_policy},
            task_id=task_id,
        )
    except Exception as exc:
        BaseRuntimeImage.objects.filter(
            pk=row.pk, status=BaseRuntimeImage.Status.BUILDING, build_task_id=task_id
        ).update(
            status=BaseRuntimeImage.Status.PENDING, build_task_id="",
            build_owner_deployment_id="", build_completed_at=timezone.now(),
            last_error=str(exc),
            last_error_details={
                "stage": "base_image_dispatch", "base_image_ref": spec.image_ref,
                "resource_policy_source": "server_owned", "retry_pending": False,
                "docker_api_reached": False, "exception_type": type(exc).__name__,
                "technical_message": str(exc) or type(exc).__name__,
            },
            updated_at=timezone.now(),
        )
        raise
    return {
        "queued": True, "cache_hit": False, "waiting": False,
        "task_id": task_id, "rebuild_requested": False,
        "image_ref": spec.image_ref,
    }
def build_registered_base_image(
    base_image_id,
    *,
    task_id: str | None = None,
    force_rebuild: bool = False,
    build_policy: dict[str, Any] | None = None,
) -> None:
    """Build one registry row while keeping retry state non-terminal.

    Celery owns the distinction between an intermediate failed attempt and
    final exhaustion. This helper never writes FAILED for a transient attempt.
    """
    from django.db import transaction
    from deployments.common.resource_policy import resolve_build_policy

    effective_policy = resolve_build_policy(build_policy)
    with transaction.atomic():
        row = BaseRuntimeImage.objects.select_for_update().get(pk=base_image_id)
        spec = _spec_for_record(row)
        fingerprint = _spec_fingerprint(spec)
        if task_id and row.status in {
            BaseRuntimeImage.Status.BUILDING,
            BaseRuntimeImage.Status.READY,
            BaseRuntimeImage.Status.FAILED,
        } and row.build_task_id and row.build_task_id != task_id:
            return
        if task_id and row.status in {
            BaseRuntimeImage.Status.READY,
            BaseRuntimeImage.Status.FAILED,
        } and not row.build_task_id:
            return
        if row.status == BaseRuntimeImage.Status.BUILDING and row.build_task_id:
            if task_id and row.build_task_id != task_id:
                return
        elif (
            row.status == BaseRuntimeImage.Status.READY
            and not row.rebuild_requested
            and not force_rebuild
            and row.definition_fingerprint == fingerprint
        ):
            return

        continuing_build = bool(
            task_id
            and row.status == BaseRuntimeImage.Status.BUILDING
            and str(row.build_task_id or "") == str(task_id)
        )
        owner_task_id = task_id or row.build_task_id or str(uuid.uuid4())
        owner_deployment_id = str(row.build_owner_deployment_id or "")
        requested_force_rebuild = bool(force_rebuild or row.rebuild_requested)
        pending_details = dict(row.last_error_details or {})
        preserved_pending = {
            key: pending_details[key]
            for key in (
                "rebuild_pending",
                "rebuild_after_current",
                "pending_definition_fingerprint",
                "pending_image_ref",
                "pending_source_image",
                "pending_image_repository",
                "pending_image_tag",
            )
            if key in pending_details
        }
        if row.rebuild_requested:
            preserved_pending["rebuild_after_current"] = True
        row.status = BaseRuntimeImage.Status.BUILDING
        row.build_task_id = owner_task_id
        row.build_owner_deployment_id = owner_deployment_id
        row.definition_fingerprint = fingerprint
        row.rebuild_requested = False
        row.build_started_at = row.build_started_at if continuing_build and row.build_started_at else timezone.now()
        row.build_completed_at = None
        row.last_error = ""
        row.last_error_details = preserved_pending
        row.save(update_fields=[
            "status", "build_task_id", "build_owner_deployment_id",
            "definition_fingerprint", "rebuild_requested",
            "build_started_at", "build_completed_at", "last_error",
            "last_error_details", "updated_at",
        ])

    try:
        def _assert_db_owner() -> None:
            if not task_id:
                return
            current = (
                BaseRuntimeImage.objects.filter(pk=base_image_id)
                .values("build_task_id", "build_started_at")
                .first()
                or {}
            )
            if str(current.get("build_task_id") or "") != str(task_id):
                raise RuntimeError(
                    "Base-image build ownership was superseded by another task or monitor recovery."
                )
            started = current.get("build_started_at")
            if started is not None:
                from core.settings_service import base_image_build_timeout_minutes
                if (timezone.now() - started).total_seconds() >= base_image_build_timeout_minutes() * 60:
                    raise TimeoutError(
                        "Base-image build exceeded the dedicated "
                        f"{base_image_build_timeout_minutes()}-minute lifecycle budget."
                    )

        _build_spec(
            spec,
            build_policy=effective_policy,
            force_rebuild=requested_force_rebuild,
            ownership_check=_assert_db_owner,
            timeout_seconds=max(
                0.1,
                (
                    timedelta(minutes=__import__("core.settings_service", fromlist=["base_image_build_timeout_minutes"]).base_image_build_timeout_minutes())
                    - (timezone.now() - row.build_started_at)
                ).total_seconds()
                if row.build_started_at
                else __import__("core.settings_service", fromlist=["base_image_build_timeout_minutes"]).base_image_build_timeout_minutes() * 60,
            ),
        )
        _assert_db_owner()
        client = get_docker_client()
        img = client.images.get(spec.image_ref)
        with transaction.atomic():
            row = BaseRuntimeImage.objects.select_for_update().get(pk=base_image_id)
            if task_id and str(row.build_task_id or "") != str(task_id):
                raise RuntimeError(
                    "Base-image build ownership changed before READY state could be committed."
                )
            requested_by_deployment = str(row.build_owner_deployment_id or "")
            pending_details = dict(row.last_error_details or {})
            rebuild_after_success = bool(
                row.rebuild_requested
                or pending_details.get("rebuild_pending")
                or pending_details.get("rebuild_after_current")
            )
            row.status = BaseRuntimeImage.Status.READY
            row.image_id = getattr(img, "id", "") or ""
            attrs = getattr(img, "attrs", {}) or {}
            digests = attrs.get("RepoDigests") or []
            row.image_digest = str(digests[0]) if digests else ""
            row.definition_fingerprint = _spec_fingerprint(spec)
            row.build_completed_at = timezone.now()
            row.build_count = (row.build_count or 0) + 1
            row.build_task_id = ""
            row.build_owner_deployment_id = ""
            row.last_error = ""
            row.last_error_details = {}
            row.save(update_fields=[
                "status", "image_id", "image_digest", "definition_fingerprint",
                "build_completed_at", "build_count", "build_task_id",
                "build_owner_deployment_id", "last_error", "last_error_details",
                "updated_at",
            ])
        if rebuild_after_success:
            try:
                pending_fp = pending_details.get("pending_definition_fingerprint")
                pending_ref = pending_details.get("pending_image_ref")
                if pending_fp and pending_ref:
                    row.variant = "apache" if row.logical_runtime == "php" else row.variant
                    row.source_image = pending_details.get("pending_source_image") or row.source_image
                    row.image_repository = pending_details.get("pending_image_repository") or row.image_repository
                    row.image_tag = pending_details.get("pending_image_tag") or row.image_tag
                    row.image_ref = pending_ref
                    row.definition_fingerprint = pending_fp
                    row.status = BaseRuntimeImage.Status.PENDING
                    row.image_id = ""
                    row.image_digest = ""
                row.rebuild_requested = False
                row.rebuild_requested_at = None
                row.save(update_fields=[
                    "variant", "source_image", "image_repository", "image_tag",
                    "image_ref", "definition_fingerprint", "status", "image_id",
                    "image_digest", "rebuild_requested", "rebuild_requested_at",
                    "last_error_details", "updated_at",
                ])
                request_base_runtime_image_build(
                    row.pk,
                    force_rebuild=not bool(pending_fp),
                    deployment_id=None,
                )
            except Exception:
                logger.exception("Failed to queue requested post-build base-image renewal for %s.", row.image_ref)
        if requested_by_deployment:
            try:
                settings = base_image_settings()
                if not settings["retain_after_deploy"]:
                    active = BaseRuntimeImageLease.objects.filter(
                        base_image=row, released_at__isnull=True
                    ).exists()
                    if not active:
                        get_docker_client().images.remove(spec.image_ref, force=False)
                        BaseRuntimeImage.objects.filter(pk=row.pk).update(
                            status=BaseRuntimeImage.Status.PENDING,
                            image_id="", image_digest="", updated_at=timezone.now(),
                        )
            except Exception as cleanup_exc:
                logger.warning(
                    "Could not cleanup unretained deployment-owned base %s: %s",
                    spec.image_ref, cleanup_exc,
                )
    except Exception as exc:
        details = dict(getattr(exc, "details", {}) or {})
        details.update({
            "stage": "base_image",
            "base_image_ref": spec.image_ref,
            "resource_policy_source": "server_owned",
            "resource_policy_complete": all(
                key in effective_policy
                for key in ("cpu", "memory_mb", "pids_limit", "shm_size_mb", "mode")
            ),
            "retry_pending": None,
            "exception_type": type(exc).__name__,
            "technical_message": str(exc) or type(exc).__name__,
        })
        BaseRuntimeImage.objects.filter(pk=base_image_id).update(
            last_error=str(exc),
            last_error_details=details,
            build_completed_at=None,
            updated_at=timezone.now(),
        )
        logger.exception(
            "Base-image build attempt failed ref=%s exception=%s; Celery decides terminal state.",
            spec.image_ref, type(exc).__name__,
        )
        raise

def _wait_for_existing_build(row_id, image_ref: str, timeout: int | None = None) -> bool:
    """Wait for DB READY; BUILDING includes both active and retry-pending attempts."""
    if timeout is None:
        from core.settings_service import base_image_timeout_minutes
        timeout = base_image_timeout_minutes() * 60
    deadline = time.time() + max(0, int(timeout))
    while time.time() < deadline:
        current = BaseRuntimeImage.objects.filter(pk=row_id).values(
            "status", "image_ref", "build_task_id"
        ).first()
        if not current:
            return False
        status = current["status"]
        if status == BaseRuntimeImage.Status.READY:
            return _docker_image_exists(image_ref)
        if status in {BaseRuntimeImage.Status.FAILED, BaseRuntimeImage.Status.DISABLED}:
            return False
        time.sleep(2)
    current = BaseRuntimeImage.objects.filter(pk=row_id).values("status").first()
    return bool(
        current
        and current["status"] == BaseRuntimeImage.Status.READY
        and _docker_image_exists(image_ref)
    )

def _mark_local_image_ready(
    row: BaseRuntimeImage,
    *,
    expected_fingerprint: str,
) -> bool:
    """Adopt a local image only when its operator definition fingerprint matches."""
    if not _docker_image_exists(row.image_ref):
        return False
    try:
        img = get_docker_client().images.get(row.image_ref)
        attrs = getattr(img, "attrs", {}) or {}
        labels = ((attrs.get("Config") or {}).get("Labels") or {})
        if labels.get("io.passdeployer.base-definition") != expected_fingerprint:
            logger.info(
                "Refusing unlabelled/stale local base image %s; expected fingerprint=%s",
                row.image_ref, expected_fingerprint,
            )
            return False
        digests = attrs.get("RepoDigests") or []
        row.status = BaseRuntimeImage.Status.READY
        row.image_id = getattr(img, "id", "") or ""
        row.image_digest = str(digests[0]) if digests else ""
        row.definition_fingerprint = expected_fingerprint
        row.last_error = ""
        row.last_error_details = {}
        row.save(update_fields=[
            "status", "image_id", "image_digest", "definition_fingerprint",
            "last_error", "last_error_details", "updated_at",
        ])
        return True
    except Exception:
        logger.exception("Failed to register existing local base image %s", row.image_ref)
        return False

def _base_image_wait_timeout_seconds(deployment_id: str | None) -> int:
    """Return only the deployment's dedicated base-image phase budget."""
    from core.settings_service import base_image_build_timeout_minutes

    if not deployment_id:
        return base_image_build_timeout_minutes() * 60
    remaining = deployment_phase_remaining_seconds(deployment_id)
    if remaining is None:
        return base_image_build_timeout_minutes() * 60
    return remaining


def _raise_base_image_failure(
    image_ref: str,
    current: dict[str, Any] | None,
    *,
    waiting_for_concurrent: bool = False,
) -> None:
    from deployments.common.exceptions import BaseImageBuildError

    current = current or {}
    raw_details = dict(current.get("last_error_details") or {})
    details = {
        **raw_details,
        "stage": "base_image",
        "base_image_ref": image_ref,
        "resource_policy_source": raw_details.get("resource_policy_source") or "server_owned",
        "retry_pending": bool(raw_details.get("retry_pending")),
        "docker_api_reached": raw_details.get("docker_api_reached"),
        "exception_type": raw_details.get("exception_type") or "RuntimeError",
        "waiting_for_concurrent": waiting_for_concurrent,
    }
    reason = (current.get("last_error") or "").strip()
    message = f"Base image build failed: {image_ref}. {reason or 'builder reported a failure without a reason'}"
    raise BaseImageBuildError(
        message,
        stage="base_image",
        technical_message=message,
        details=details,
    )


def ensure_base_images(config, *, build_policy=None, logger_sink=None, deployment_id: str | None = None) -> dict[str, str]:
    policy = base_image_settings()
    if not policy["enabled"]:
        return {}

    from django.db import IntegrityError
    from deployments.common.exceptions import BaseImageBuildError
    from deployments.common.resource_policy import resolve_build_policy

    effective_build_policy = resolve_build_policy(build_policy)
    try:
        release_stale_base_image_leases()
    except Exception:
        logger.exception("Failed to reconcile stale base image leases")
    specs = make_specs(config)
    if not specs:
        return {}

    host = _host_key()
    result: dict[str, str] = {}
    for spec in specs:
        key = f"{spec.logical_runtime}:{spec.version}:{spec.variant}"
        fingerprint = _spec_fingerprint(spec)
        with transaction.atomic():
            row = (
                BaseRuntimeImage.objects.select_for_update().filter(
                    logical_runtime=spec.logical_runtime,
                    runtime_version=spec.version,
                    variant=spec.variant,
                    architecture="",
                    docker_host=host,
                ).first()
            )
            if row is None:
                try:
                    with transaction.atomic():
                        row = BaseRuntimeImage.objects.create(
                            logical_runtime=spec.logical_runtime,
                            runtime_version=spec.version,
                            variant=spec.variant,
                            architecture="",
                            docker_host=host,
                            source_image=spec.source_image,
                            image_repository=spec.repository,
                            image_tag=spec.tag,
                            image_ref=spec.image_ref,
                            definition_fingerprint=fingerprint,
                            status=BaseRuntimeImage.Status.PENDING,
                            enabled=True,
                            auto_build=True,
                        )
                except IntegrityError:
                    # Another deployment won the unique identity race. The
                    # outer transaction remains usable because the create was
                    # isolated inside a savepoint.
                    row = BaseRuntimeImage.objects.select_for_update().get(
                        logical_runtime=spec.logical_runtime,
                        runtime_version=spec.version,
                        variant=spec.variant,
                        architecture="",
                        docker_host=host,
                    )
            if not row.enabled:
                raise RuntimeError(f"Base runtime image {key} is disabled by an administrator.")

            definition_changed = row.definition_fingerprint != fingerprint
            if row.status == BaseRuntimeImage.Status.BUILDING:
                if definition_changed:
                    pending = dict(row.last_error_details or {})
                    pending.update({
                        "rebuild_pending": True,
                        "pending_definition_fingerprint": fingerprint,
                        "pending_image_ref": spec.image_ref,
                        "pending_source_image": spec.source_image,
                        "pending_image_repository": spec.repository,
                        "pending_image_tag": spec.tag,
                    })
                    row.rebuild_requested = True
                    row.rebuild_requested_at = timezone.now()
                    row.last_error_details = pending
                    row.save(update_fields=[
                        "rebuild_requested", "rebuild_requested_at",
                        "last_error_details", "updated_at",
                    ])
            elif definition_changed or any(
                getattr(row, field) != value
                for field, value in {
                    "source_image": spec.source_image,
                    "image_repository": spec.repository,
                    "image_tag": spec.tag,
                    "image_ref": spec.image_ref,
                }.items()
            ):
                row.source_image = spec.source_image
                row.image_repository = spec.repository
                row.image_tag = spec.tag
                row.image_ref = spec.image_ref
                row.definition_fingerprint = fingerprint
                row.status = BaseRuntimeImage.Status.PENDING
                row.rebuild_requested = bool(definition_changed)
                row.rebuild_requested_at = timezone.now() if definition_changed else row.rebuild_requested_at
                if definition_changed:
                    row.image_id = ""
                    row.image_digest = ""
                    row.last_error = ""
                    row.last_error_details = {}
                row.save(update_fields=[
                    "source_image", "image_repository", "image_tag", "image_ref",
                    "definition_fingerprint", "status", "rebuild_requested",
                    "rebuild_requested_at", "image_id", "image_digest",
                    "last_error", "last_error_details", "updated_at",
                ])

            local_exists = _docker_image_exists(row.image_ref)
            local_compatible = (
                local_exists
                and _local_image_matches_fingerprint(row.image_ref, fingerprint)
            )

            if (
                policy["auto_register_existing"]
                and _can_use_compatible_local_base_image(
                    row,
                    fingerprint,
                    local_exists=local_exists,
                    local_compatible=local_compatible,
                )
            ):
                # A matching local image is already a valid artifact. Do not
                # let BUILDING/rebuild_requested registry state block an
                # application deployment; an active operator renewal may keep
                # running independently, and stale state can no longer create
                # a false "wait for shared build" dependency.
                if row.status != BaseRuntimeImage.Status.BUILDING:
                    _mark_local_image_ready(row, expected_fingerprint=fingerprint)
                result[logical_key(spec)] = row.image_ref
                if deployment_id:
                    acquire_base_image_leases([row.image_ref], deployment_id)
                if logger_sink:
                    logger_sink.info(
                        "base_image",
                        f"Using compatible local base image {row.image_ref}.",
                        progress=18,
                        details={
                            "image": row.image_ref,
                            "runtime": key,
                            "cache": "compatible-local",
                            "definition_fingerprint": fingerprint,
                            "registry_status": row.status,
                            "rebuild_requested": bool(row.rebuild_requested),
                            "background_build_task_id": str(row.build_task_id or ""),
                        },
                    )
                continue
            if logger_sink:
                    logger_sink.info(
                        "base_image",
                        f"Registered compatible local base image {row.image_ref}.",
                        progress=17,
                        details={
                            "image": row.image_ref, "runtime": key, "cache": "adopted",
                            "definition_fingerprint": fingerprint,
                        },
                    )
                continue

            if logger_sink:
                logger_sink.info(
                    "base_image",
                    f"Base image resolution: runtime={key}, image={row.image_ref}, status={row.status}, docker_local={local_exists}, rebuild_requested={row.rebuild_requested}.",
                    progress=17,
                    details={
                        "image": row.image_ref, "runtime": key, "status": row.status,
                        "docker_local": local_exists, "rebuild_requested": bool(row.rebuild_requested),
                        "definition_fingerprint": fingerprint,
                    },
                )
            if row.status == BaseRuntimeImage.Status.READY and local_compatible and not row.rebuild_requested and row.definition_fingerprint == fingerprint:
                result[logical_key(spec)] = row.image_ref
                if deployment_id:
                    acquire_base_image_leases([row.image_ref], deployment_id)
                if logger_sink:
                    logger_sink.info(
                        "base_image",
                        f"Using cached base image {row.image_ref}.",
                        progress=17,
                        details={"image": row.image_ref, "runtime": key, "cache": "hit", "definition_fingerprint": fingerprint},
                    )
                continue

            if deployment_id:
                mark_base_image_phase_started(deployment_id)

            effective_auto_build = bool(row.auto_build and policy["auto_build"])
            if not effective_auto_build and not local_exists:
                raise RuntimeError(
                    f"Base runtime image {key} is not cached locally and auto-build is disabled. "
                    "Enable Auto Build or rebuild it from the admin panel."
                )

            if row.status == BaseRuntimeImage.Status.BUILDING:
                age_seconds = 0
                if row.build_started_at:
                    age_seconds = max(0, (timezone.now() - row.build_started_at).total_seconds())
                if age_seconds > _base_image_wait_timeout_seconds(None) and not local_exists:
                    previous_task_id = str(row.build_task_id or "")
                    recovery_owner = f"base-recovery-{uuid.uuid4()}"
                    owner = True
                    row.status = BaseRuntimeImage.Status.BUILDING
                    row.build_started_at = timezone.now()
                    row.build_task_id = recovery_owner
                    row.build_owner_deployment_id = ""
                    row.last_error = "Recovered stale base-image build."
                    row.last_error_details = {
                        "stage": "base_image", "retry_pending": False,
                        "recovered_stale": True, "superseded_task_id": previous_task_id,
                    }
                    row.save(update_fields=[
                        "status", "build_started_at", "build_task_id",
                        "build_owner_deployment_id", "last_error",
                        "last_error_details", "updated_at",
                    ])
                else:
                    row_id = row.pk
                    image_ref = row.image_ref
                    owner = False
            else:
                owner = True
                row.status = BaseRuntimeImage.Status.BUILDING
                row.build_started_at = timezone.now()
                row.build_completed_at = None
                row.last_error = ""
                row.last_error_details = dict(row.last_error_details or {})
                row.save(update_fields=["status", "build_started_at", "build_completed_at", "last_error", "last_error_details", "updated_at"])

        if not owner:
            if logger_sink:
                logger_sink.info(
                    "base_image",
                    f"Base runtime image {image_ref} is currently being built by another worker. Waiting for the shared build to complete.",
                    progress=17,
                    details={
                        "image": image_ref, "runtime": key, "cache": "waiting",
                        "waiting_for_existing_build": True,
                        "owner_task_id": str(row.build_task_id or ""),
                        "build_started_at": row.build_started_at.isoformat() if row.build_started_at else None,
                    },
                )
            timeout = _base_image_wait_timeout_seconds(deployment_id)
            if _wait_for_existing_build(row_id, image_ref, timeout=timeout):
                current = BaseRuntimeImage.objects.filter(pk=row_id).values(
                    "status", "definition_fingerprint", "rebuild_requested"
                ).first()
                if (
                    current
                    and current["status"] == BaseRuntimeImage.Status.READY
                    and current["definition_fingerprint"] == fingerprint
                    and not current["rebuild_requested"]
                ):
                    result[logical_key(spec)] = image_ref
                    if deployment_id:
                        acquire_base_image_leases([image_ref], deployment_id)
                    if logger_sink:
                        logger_sink.info(
                            "base_image",
                            f"Waited for concurrent base image build {image_ref}; cache hit.",
                            progress=18, details={"image": image_ref, "runtime": key, "cache": "waited"},
                        )
                    continue
                continue
            current = BaseRuntimeImage.objects.filter(pk=row_id).values(
                "status", "image_ref", "last_error", "last_error_details"
            ).first()
            if current and current["status"] == BaseRuntimeImage.Status.FAILED:
                _raise_base_image_failure(image_ref, current, waiting_for_concurrent=True)
            raise BaseImageBuildError(
                f"The required base runtime image {image_ref} could not become ready within the base-image build/wait limit.",
                stage="base_image",
                details={
                    "stage": "base_image", "base_image_ref": image_ref,
                    "resource_policy_source": "server_owned",
                    "timeout_phase": "base_image",
                    "timeout_minutes": round(timeout / 60, 2),
                    "retry_pending": bool((current or {}).get("last_error_details", {}).get("retry_pending")),
                    "builder_state": (current or {}).get("status"),
                    "docker_api_reached": (current or {}).get("last_error_details", {}).get("docker_api_reached"),
                },
            )

        task_dispatched = False
        task_id = ""
        if logger_sink:
            logger_sink.info(
                "base_image",
                f"Queueing dedicated base-image build {spec.image_ref}.",
                progress=17,
                details={
                    "image": spec.image_ref, "runtime": key, "cache": "miss",
                    "source_image": spec.source_image, "resource_policy_source": "server_owned",
                    "resource_policy_complete": True,
                },
            )
        try:
            if deployment_id:
                acquire_base_image_leases([spec.image_ref], deployment_id)
            task_id = f"base-image-{row.pk}-{uuid.uuid4()}"
            BaseRuntimeImage.objects.filter(pk=row.pk, status=BaseRuntimeImage.Status.BUILDING).update(
                build_task_id=task_id,
                build_owner_deployment_id=str(deployment_id or "")[:255],
                updated_at=timezone.now(),
            )
            from deployments.celery.tasks import build_base_runtime_image
            build_base_runtime_image.apply_async(
                args=[str(row.pk)],
                kwargs={"build_policy": effective_build_policy},
                task_id=task_id,
            )
            task_dispatched = True
            timeout = _base_image_wait_timeout_seconds(deployment_id)
            if not _wait_for_existing_build(row.pk, spec.image_ref, timeout=timeout):
                current = BaseRuntimeImage.objects.filter(pk=row.pk).values(
                    "status", "image_ref", "last_error", "last_error_details"
                ).first()
                if current and current["status"] == BaseRuntimeImage.Status.FAILED:
                    _raise_base_image_failure(spec.image_ref, current)
                raise BaseImageBuildError(
                    f"The required base runtime image {spec.image_ref} could not become ready within the base-image build/wait limit.",
                    stage="base_image",
                    details={
                        "stage": "base_image", "base_image_ref": spec.image_ref,
                        "resource_policy_source": "server_owned",
                        "timeout_phase": "base_image",
                        "timeout_minutes": round(timeout / 60, 2),
                        "retry_pending": bool((current or {}).get("last_error_details", {}).get("retry_pending")),
                    },
                )
            result[logical_key(spec)] = spec.image_ref
        except BaseImageBuildError:
            raise
        except Exception as exc:
            if task_dispatched:
                raise
            details = {
                "stage": "base_image_dispatch", "base_image_ref": spec.image_ref,
                "resource_policy_source": "server_owned", "retry_pending": False,
                "docker_api_reached": False, "exception_type": type(exc).__name__,
                "technical_message": str(exc) or type(exc).__name__,
            }
            dispatch_filter = {
                "pk": row.pk,
                "status": BaseRuntimeImage.Status.BUILDING,
            }
            if task_id:
                dispatch_filter["build_task_id"] = task_id
            BaseRuntimeImage.objects.filter(**dispatch_filter).update(
                status=BaseRuntimeImage.Status.PENDING, build_task_id="", build_owner_deployment_id="",
                last_error=str(exc), last_error_details=details,
                build_completed_at=timezone.now(), updated_at=timezone.now(),
            )
            raise
    return result


def release_stale_base_image_leases(max_age_hours: int = 24) -> int:
    """Release leases left behind by workers that died without running finally."""
    from deploy.models import Deploy, DeploymentStatusChoices

    cutoff = timezone.now() - timedelta(hours=max(1, max_age_hours))
    terminal = {
        DeploymentStatusChoices.SUCCEEDED,
        DeploymentStatusChoices.FAILED,
        DeploymentStatusChoices.ROLLED_BACK,
        DeploymentStatusChoices.CANCELLED,
    }
    count = 0
    stale = BaseRuntimeImageLease.objects.filter(
        released_at__isnull=True,
        acquired_at__lt=cutoff,
    ).only("id", "deployment_id")
    for lease in stale.iterator():
        deploy = Deploy.objects.filter(pk=lease.deployment_id).only("status").first()
        if deploy is not None and deploy.status not in terminal:
            continue
        updated = BaseRuntimeImageLease.objects.filter(
            pk=lease.pk,
            released_at__isnull=True,
        ).update(released_at=timezone.now(), updated_at=timezone.now())
        count += updated
    if count:
        logger.warning("Released %d stale base image lease(s).", count)
    return count


def acquire_base_image_leases(
    image_refs: list[str] | tuple[str, ...],
    deployment_id: str | None,
) -> None:
    """Create active deployment leases for the resolved base-image references."""
    if not deployment_id or not image_refs:
        return

    refs = sorted({str(ref).strip() for ref in image_refs if str(ref).strip()})
    if not refs:
        return

    deployment_id = str(deployment_id)[:255]
    for ref in refs:
        row = (
            BaseRuntimeImage.objects
            .filter(image_ref=ref)
            .order_by("-updated_at")
            .first()
        )
        if row is None:
            logger.warning(
                "Cannot acquire base-image lease: registry row not found for %s",
                ref,
            )
            continue

        BaseRuntimeImageLease.objects.update_or_create(
            base_image=row,
            deployment_id=deployment_id,
            defaults={"released_at": None},
        )


def release_base_image_leases(
    deployment_id: str | None,
    *,
    remove_if_unretained: bool = False,
) -> None:
    """Release all active base-image leases owned by one deployment."""
    if not deployment_id:
        return

    deployment_id = str(deployment_id)[:255]
    leases = list(
        BaseRuntimeImageLease.objects
        .select_related("base_image")
        .filter(
            deployment_id=deployment_id,
            released_at__isnull=True,
        )
    )
    if not leases:
        return

    now = timezone.now()
    client = None

    for lease in leases:
        lease.released_at = now
        lease.save(update_fields=["released_at", "updated_at"])

        if not remove_if_unretained:
            continue

        try:
            with transaction.atomic():
                locked = (
                    BaseRuntimeImage.objects
                    .select_for_update()
                    .get(pk=lease.base_image.pk)
                )
                active = BaseRuntimeImageLease.objects.filter(
                    base_image=locked,
                    released_at__isnull=True,
                ).exists()
                if active:
                    continue

                if client is None:
                    client = get_docker_client()

                client.images.remove(locked.image_ref, force=False)
                locked.status = BaseRuntimeImage.Status.PENDING
                locked.image_id = ""
                locked.image_digest = ""
                locked.save(
                    update_fields=[
                        "status",
                        "image_id",
                        "image_digest",
                        "updated_at",
                    ]
                )
                logger.info(
                    "Removed unretained base runtime image %s after deployment %s",
                    locked.image_ref,
                    deployment_id,
                )
        except Exception as exc:
            # Lease release itself succeeded. Physical cleanup is best-effort;
            # a failed remove must not make deployment completion fail.
            logger.warning(
                "Unable to remove unretained base image %s: %s",
                lease.base_image.image_ref,
                exc,
            )


def logical_key(spec: BaseImageSpec) -> str:
    """Return the stable configuration key used for resolved base images."""
    if spec.logical_runtime == "php":
        return "base_image"
    if spec.logical_runtime == "node":
        return "node_base_image"
    if spec.logical_runtime == "nginx":
        return "nginx_base_image"
    if spec.logical_runtime == "python":
        return "base_image"
    if spec.logical_runtime == "go":
        return "base_image"
    return "base_image"
