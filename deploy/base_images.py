"""Base runtime image registry and resolver for application deployments.

Base images contain only operator-owned runtime/tooling layers. Application
sources and tenant dependencies are intentionally never copied into them.
"""
from __future__ import annotations

import io
import logging
import os
import re
import socket
import tarfile
import time
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


def _php(version: str, *, public_root: bool = True) -> BaseImageSpec:
    src = f"{_docker_mirror()}/php:{version}-apache"
    variant = "apache-public" if public_root else "apache-root"
    repository = "paas-base/php-apache" if public_root else "paas-base/php-apache-root"
    doc_root = "/var/www/html/public" if public_root else "/var/www/html"
    return BaseImageSpec(
        "php", version, variant, src, repository, f"{_tag_token(version)}-r1",
        f'''FROM {src}

ENV APACHE_DOCUMENT_ROOT={doc_root}\\
    COMPOSER_ALLOW_SUPERUSER=1\\
    COMPOSER_MEMORY_LIMIT=-1

WORKDIR /var/www/html

RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev \
        libicu-dev libonig-dev libxml2-dev curl ca-certificates \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j$(nproc) mysqli pdo pdo_mysql opcache zip gd intl bcmath mbstring exif pcntl \
    && a2enmod rewrite headers mime dir expires alias \
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
    && printf '%s\n' 'ServerName localhost' > /etc/apache2/conf-available/deployer-server-name.conf \
    && a2enconf deployer-server-name \
    && printf '%s\n' \
       '<VirtualHost *:80>' \
       '    ServerName localhost' \
       '    DocumentRoot {doc_root}' \
       '    <Directory {doc_root}>' \
       '        AllowOverride All' \
       '        Require all granted' \
       '        Options FollowSymLinks' \
       '    </Directory>' \
       '    RewriteEngine On' \
       '    RewriteCond %{{REQUEST_FILENAME}} -f [OR]' \
       '    RewriteCond %{{REQUEST_FILENAME}} -d' \
       '    RewriteRule ^ - [END]' \
       '    RewriteCond %{{REQUEST_FILENAME}} !-f' \
       '    RewriteCond %{{REQUEST_FILENAME}} !-d' \
       '    RewriteRule ^ index.php [L]' \
       '</VirtualHost>' \
       > /etc/apache2/sites-available/000-default.conf \
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
        specs.append(_php(version, public_root=platform != "php"))
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


def _build_spec(spec: BaseImageSpec, *, build_policy: dict[str, Any] | None = None, on_output=None):
    logger.info("Building base runtime image %s from %s", spec.image_ref, spec.source_image)
    image = Image(
        spec.repository,
        spec.tag,
        spec.dockerfile,
        _tar_for_dockerfile(spec.dockerfile),
        build_resource_policy=build_policy or {},
        build_options={"pull": True, "no_cache": True},
        deployment_id=f"base:{spec.image_ref}",
    )
    return image.create(on_build_output=on_output)


def _spec_for_record(row: BaseRuntimeImage) -> BaseImageSpec:
    runtime = str(row.logical_runtime or "").lower()
    version = str(row.runtime_version or "")
    variant = str(row.variant or "default")
    if runtime == "php":
        return _php(version, public_root=variant != "apache-root")
    if runtime == "python":
        return _python(version)
    if runtime == "node":
        return _node(version)
    if runtime == "nginx":
        return _nginx(version)
    if runtime == "go":
        return _go(version)
    raise ValueError(f"Unsupported base runtime '{runtime}'")


def build_registered_base_image(base_image_id) -> None:
    """Rebuild an existing registry row, used by admin and recovery tasks."""
    from django.db import transaction

    with transaction.atomic():
        row = BaseRuntimeImage.objects.select_for_update().get(pk=base_image_id)
        spec = _spec_for_record(row)
        row.status = BaseRuntimeImage.Status.BUILDING
        row.rebuild_requested = False
        row.build_started_at = timezone.now()
        row.last_error = ""
        row.save(update_fields=["status", "rebuild_requested", "build_started_at", "last_error", "updated_at"])

    try:
        _build_spec(spec)
        client = get_docker_client()
        img = client.images.get(spec.image_ref)
        row = BaseRuntimeImage.objects.get(pk=base_image_id)
        row.status = BaseRuntimeImage.Status.READY
        row.image_id = getattr(img, "id", "") or ""
        row.image_digest = str((getattr(img, "attrs", {}) or {}).get("RepoDigests", [""])[0] or "") if (getattr(img, "attrs", {}) or {}).get("RepoDigests") else ""
        row.build_completed_at = timezone.now()
        row.build_count = (row.build_count or 0) + 1
        row.last_error = ""
        row.save(update_fields=["status", "image_id", "image_digest", "build_completed_at", "build_count", "last_error", "updated_at"])
    except Exception as exc:
        BaseRuntimeImage.objects.filter(pk=base_image_id).update(
            status=BaseRuntimeImage.Status.FAILED,
            last_error=str(exc),
            build_completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise


def _wait_for_existing_build(row_id, image_ref: str, timeout: int = 900) -> bool:
    deadline = time.time() + max(30, timeout)
    while time.time() < deadline:
        if _docker_image_exists(image_ref):
            return True
        current = BaseRuntimeImage.objects.filter(pk=row_id).values("status", "image_ref").first()
        if not current:
            return False
        if current["status"] in {BaseRuntimeImage.Status.FAILED, BaseRuntimeImage.Status.DISABLED}:
            return False
        time.sleep(2)
    return _docker_image_exists(image_ref)


def _mark_local_image_ready(row: BaseRuntimeImage) -> bool:
    if not _docker_image_exists(row.image_ref):
        return False
    try:
        img = get_docker_client().images.get(row.image_ref)
        attrs = getattr(img, "attrs", {}) or {}
        digests = attrs.get("RepoDigests") or []
        row.status = BaseRuntimeImage.Status.READY
        row.image_id = getattr(img, "id", "") or ""
        row.image_digest = str(digests[0]) if digests else ""
        row.last_error = ""
        row.save(update_fields=["status", "image_id", "image_digest", "last_error", "updated_at"])
        return True
    except Exception:
        logger.exception("Failed to register existing local base image %s", row.image_ref)
        return False


def ensure_base_images(config, *, build_policy=None, logger_sink=None, deployment_id: str | None = None) -> dict[str, str]:
    policy = base_image_settings()
    try:
        release_stale_base_image_leases()
    except Exception:
        logger.exception("Failed to reconcile stale base image leases")
    specs = make_specs(config)
    if not specs or not policy["enabled"]:
        return {}

    host = _host_key()
    result: dict[str, str] = {}
    for spec in specs:
        key = f"{spec.logical_runtime}:{spec.version}:{spec.variant}"
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
                    status=BaseRuntimeImage.Status.PENDING,
                    enabled=True,
                    auto_build=True,
                )
            else:
                changed = False
                for field, value in {
                    "source_image": spec.source_image,
                    "image_repository": spec.repository,
                    "image_tag": spec.tag,
                    "image_ref": spec.image_ref,
                }.items():
                    if getattr(row, field) != value:
                        setattr(row, field, value)
                        changed = True
                if changed:
                    row.status = BaseRuntimeImage.Status.PENDING
                    row.save(update_fields=["source_image", "image_repository", "image_tag", "image_ref", "status", "updated_at"])

            # A Docker image may survive a DB reset/manual row deletion. Adopt it
            # instead of paying to rebuild an already available base.
            if policy["auto_register_existing"] and row.enabled and _mark_local_image_ready(row):
                result[logical_key(spec)] = row.image_ref
                if deployment_id:
                    acquire_base_image_leases([row.image_ref], deployment_id)
                if logger_sink:
                    logger_sink.info(
                        "base_image",
                        f"Registered existing local base image {row.image_ref}.",
                        progress=17,
                        details={"image": row.image_ref, "runtime": key, "cache": "adopted"},
                    )
                continue

            if not row.enabled:
                raise RuntimeError(f"Base runtime image {key} is disabled by an administrator.")

            local_exists = _docker_image_exists(row.image_ref)
            if row.status == BaseRuntimeImage.Status.READY and local_exists:
                result[logical_key(spec)] = row.image_ref
                if deployment_id:
                    acquire_base_image_leases([row.image_ref], deployment_id)
                if logger_sink:
                    logger_sink.info(
                        "base_image",
                        f"Using cached base image {row.image_ref}.",
                        progress=17,
                        details={"image": row.image_ref, "runtime": key, "cache": "hit"},
                    )
                continue
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
                if age_seconds > 1200 and not local_exists:
                    # Builder worker died without finalising the DB row. Reclaim
                    # after 20 minutes instead of making future deployments wait forever.
                    owner = True
                    row.status = BaseRuntimeImage.Status.BUILDING
                    row.build_started_at = timezone.now()
                    row.last_error = "Recovered stale base-image build."
                    row.save(update_fields=["status", "build_started_at", "last_error", "updated_at"])
                else:
                    row_id = row.pk
                    image_ref = row.image_ref
                    owner = False
            else:
                owner = True
                row.status = BaseRuntimeImage.Status.BUILDING
                row.build_started_at = timezone.now()
                row.last_error = ""
                row.save(update_fields=["status", "build_started_at", "last_error", "updated_at"])

        if not owner:
            if _wait_for_existing_build(row_id, image_ref):
                result[logical_key(spec)] = image_ref
                if logger_sink:
                    logger_sink.info("base_image", f"Waited for concurrent base image build {image_ref}; cache hit.", progress=18,
                                     details={"image": image_ref, "runtime": key, "cache": "waited"})
                continue
            # The other builder failed. A deployment should surface that failure,
            # rather than starting a second uncontrolled build.
            raise RuntimeError(f"Concurrent base image build failed or timed out: {image_ref}")

        try:
            if logger_sink:
                logger_sink.info("base_image", f"Building missing base image {spec.image_ref}.", progress=17,
                                 details={"image": spec.image_ref, "runtime": key, "cache": "miss", "source_image": spec.source_image})
            _build_spec(spec, build_policy=build_policy)
            client = get_docker_client()
            img = client.images.get(spec.image_ref)
            attrs = getattr(img, "attrs", {}) or {}
            digests = attrs.get("RepoDigests") or []
            BaseRuntimeImage.objects.filter(pk=row.pk).update(
                status=BaseRuntimeImage.Status.READY,
                image_id=getattr(img, "id", "") or "",
                image_digest=str(digests[0]) if digests else "",
                build_completed_at=timezone.now(),
                last_error="",
                build_count=(row.build_count or 0) + 1,
                updated_at=timezone.now(),
            )
            result[logical_key(spec)] = spec.image_ref
        except Exception as exc:
            BaseRuntimeImage.objects.filter(pk=row.pk).update(
                status=BaseRuntimeImage.Status.FAILED,
                last_error=str(exc),
                build_completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if logger_sink:
                logger_sink.error("base_image", f"Base image {spec.image_ref} failed: {exc}", progress=18,
                                  details={"image": spec.image_ref, "error": str(exc)})
            raise
    return result

def release_stale_base_image_leases(max_age_hours: int = 24) -> int:
    """Release leases left behind by workers that died without running finally."""
    from deploy.models import Deploy, DeploymentStatusChoices

    cutoff = timezone.now() - __import__("datetime").timedelta(hours=max(1, max_age_hours))
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
            pk=lease.pk, released_at__isnull=True
        ).update(released_at=timezone.now(), updated_at=timezone.now())
        count += updated
    if count:
        logger.warning("Released %d stale base image lease(s).", count)
    return count


def acquire_base_image_leases(image_refs: list[str] | tuple[str, ...], deployment_id: str | None) -> None:
    if not deployment_id or not image_refs:
        return
    refs = sorted({str(ref) for ref in image_refs if ref})
    if not refs:
        return
    for ref in refs:
        row = BaseRuntimeImage.objects.filter(image_ref=ref).order_by("-updated_at").first()
        if row is None:
            continue
        BaseRuntimeImageLease.objects.get_or_create(
            base_image=row,
            deployment_id=str(deployment_id)[:255],
            defaults={"released_at": None},
        )


def release_base_image_leases(deployment_id: str | None, *, remove_if_unretained: bool = False) -> None:
    if not deployment_id:
        return
    leases = list(BaseRuntimeImageLease.objects.select_related("base_image").filter(
        deployment_id=str(deployment_id)[:255], released_at__isnull=True
    ))
    now = timezone.now()
    client = None
    for lease in leases:
        lease.released_at = now
        lease.save(update_fields=["released_at", "updated_at"])
        if not remove_if_unretained:
            continue
        try:
            with transaction.atomic():
                locked = BaseRuntimeImage.objects.select_for_update().get(pk=lease.base_image.pk)
                active = BaseRuntimeImageLease.objects.filter(
                    base_image=locked, released_at__isnull=True
                ).exists()
                if active:
                    continue
                if client is None:
                    client = get_docker_client()
                client.images.remove(locked.image_ref, force=False)
                locked.status = BaseRuntimeImage.Status.PENDING
                locked.image_id = ""
                locked.image_digest = ""
                locked.save(update_fields=["status", "image_id", "image_digest", "updated_at"])
                logger.info("Removed unretained base runtime image %s after deployment %s", locked.image_ref, deployment_id)
        except Exception as exc:
            logger.warning("Unable to remove unretained base image %s: %s", lease.base_image.image_ref, exc)


def logical_key(spec: BaseImageSpec) -> str:
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
