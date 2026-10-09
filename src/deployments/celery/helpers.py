"""deployments/celery/helpers.py — mirrors + versions from DB settings."""
from dataclasses import dataclass
import json
import logging
import os
import re
import zipfile

from deploy.models import Deploy
from core.global_settings.config import Config
from deployments.core.manager.container_manager import Container
from deployments.core.manager.image_manager import Image
from deployments.common.docker_identity import canonical_image_ref


@dataclass(frozen=True)
class MockOrchestratorResult:
    success: bool
    stage: str
    message: str
    error: str = ""
    rollback_performed: bool = False
    status: str = ""


logger = logging.getLogger(__name__)


class DeploymentHelper:
    _DOCKERFILE_ALIASES = {
        "vuejs": "vue",
        "vue": "vue",
        "statichtmlcss": "static",
        "static": "static",
        "html": "static",
        "fastapi": "python",
        # Framework-specific templates preferred; fall back to php in
        # get_dockerfile_text if Config.<framework> is missing.
        "symfony": "php",
        "codeigniter": "php",
        "lumen": "laravel",
    }

    @staticmethod
    def _runtime_format_kwargs(
        overrides: dict | None = None,
        *,
        platform: str | None = None,
    ) -> dict:
        # Prefer DB-backed settings; fall back to module constants.
        try:
            from core import settings_service as svc

            mirror_docker = svc.mirror_docker()
            mirror_python = svc.mirror_python()
            mirror_npm = svc.mirror_npm()
            mirror_apt = svc.mirror_apt()
            try:
                mirror_composer = svc.mirror_composer()
            except Exception:
                mirror_composer = ""
            versions = dict(svc.default_runtime_versions() or {})
            ports_map = dict(svc.default_ports_map() or {})
            default_expose = svc.default_expose_port()
            build_dir = svc.default_spa_build_dir()
            pip_timeout = svc.get_int("deploy.pip_timeout", 120)
        except Exception:
            from core.global_settings import config as _gcfg

            mirror_docker = getattr(_gcfg, "MIRROR_DOCKER", "docker.io")
            mirror_python = getattr(
                _gcfg, "MIRROR_PYTHON", "https://pypi.org/simple"
            )
            mirror_npm = "https://registry.npmjs.org"
            mirror_apt = ""
            mirror_composer = getattr(_gcfg, "MIRROR_COMPOSER", "") or ""
            versions = dict(getattr(_gcfg, "DEFAULT_RUNTIME_VERSIONS", None) or {})
            try:
                from core.global_settings.config import default_ports, DEFAULT_EXPOSE_PORT

                ports_map = dict(default_ports)
                default_expose = DEFAULT_EXPOSE_PORT
            except Exception:
                ports_map = {}
                default_expose = 80
            build_dir = "dist"
            pip_timeout = 120

        if not versions:
            versions = {
                "python_version": "3.11",
                "django_python_version": "3.10",
                "node_version": "20",
                "php_version": "8.2",
                "go_version": "1.21",
                "dotnet_version": "6.0",
                "nginx_version": "alpine",
            }
        # Laravel 11+/13 and modern lockfiles need 8.3+; default 8.4 when
        # the caller did not pass php_version (dockerfile.py may still bump
        # further from composer.json).
        if (platform or "").lower() in ("laravel", "lumen") and not (
            overrides or {}
        ).get("php_version"):
            versions["php_version"] = "8.4"

        kwargs = {
            "MIRROR_DOCKER": mirror_docker,
            "MIRROR_PYTHON": mirror_python,
            "MIRROR_NPM": mirror_npm,
            "MIRROR_APT": mirror_apt or "http://deb.debian.org/debian/",
            "MIRROR_COMPOSER": (mirror_composer or "").strip(),
            "PIP_DEFAULT_TIMEOUT": str(pip_timeout),
            "build_dir": build_dir,
        }
        kwargs.update(versions)

        p = (platform or "").lower().strip()
        port = ports_map.get(p)
        if port is None:
            port = default_expose
        try:
            kwargs["port"] = int(port)
        except (TypeError, ValueError):
            kwargs["port"] = default_expose

        if overrides:
            for key in versions:
                val = overrides.get(key)
                if val is not None and str(val).strip():
                    kwargs[key] = str(val).strip().lstrip("vV")
            raw_port = overrides.get("port")
            if raw_port is not None and str(raw_port).strip() != "":
                try:
                    kwargs["port"] = int(raw_port)
                except (TypeError, ValueError):
                    pass
            if overrides.get("build_dir"):
                kwargs["build_dir"] = (
                    str(overrides["build_dir"]).strip().lstrip("./").rstrip("/")
                )
        return kwargs

    @staticmethod
    def get_dockerfile_from_archive(zip_path: str) -> str | None:
        """Read a catalog/user supplied Dockerfile from the root of a ZIP.

        Only an exact root-level ``Dockerfile`` is accepted. Archive safety is
        delegated to the same primitives used by the normal deployment
        extractor; symlinks and unsafe names are rejected here as well.
        """
        if not zip_path or not os.path.isfile(zip_path):
            return None
        from deployments.common.security import is_safe_archive_name, is_zip_symlink

        with zipfile.ZipFile(zip_path, 'r') as zf:
            matches = []
            for info in zf.infolist():
                name = info.filename.replace('\\', '/')
                if not is_safe_archive_name(name):
                    raise ValueError(f"Unsafe path in deployment ZIP: {info.filename}")
                if is_zip_symlink(info):
                    raise ValueError(f"Deployment ZIP contains a symlink: {info.filename}")
                if name == 'Dockerfile':
                    matches.append(info)
            if not matches:
                return None
            if len(matches) > 1:
                raise ValueError('Deployment ZIP contains duplicate root Dockerfile entries.')
            text = zf.read(matches[0]).decode('utf-8')
            if not text.strip():
                raise ValueError('Deployment ZIP Dockerfile is empty.')
            return text

    @staticmethod
    def get_dockerfile_text(
        platform: str,
        *,
        version_overrides: dict | None = None,
    ) -> str | None:
        key = (platform or "").lower().strip()
        attr = DeploymentHelper._DOCKERFILE_ALIASES.get(key, key)

        # Candidate attribute names in priority order.
        # Laravel MUST try Config.laravel before falling back to Config.php
        # so framework-specific templates are not silently replaced by plain PHP.
        candidates: list[str] = []
        for name in (key, attr, "php" if key in ("laravel", "lumen", "symfony", "codeigniter") else None):
            if name and name not in candidates:
                candidates.append(name)

        # Prefer in-code Config for PHP family — DB templates are often stale.
        _prefer_code = any(
            c in ("php", "laravel") for c in candidates
        ) or key in ("php", "laravel", "symfony", "codeigniter", "lumen")

        raw = None
        if _prefer_code:
            for name in candidates:
                raw = getattr(Config, name, None)
                if raw:
                    break

        if not raw:
            try:
                from core import settings_service as svc

                for name in candidates:
                    raw = svc.dockerfile_template(name)
                    if raw:
                        break
            except Exception:
                pass

        if not raw:
            for name in candidates:
                raw = getattr(Config, name, None)
                if raw:
                    break
        if not raw:
            return None

        fmt = DeploymentHelper._runtime_format_kwargs(
            version_overrides, platform=key
        )
        try:
            return raw.format(**fmt)
        except KeyError:
            out = raw
            for k, v in fmt.items():
                out = out.replace("{" + k + "}", str(v))
            return out

    @staticmethod
    def _restart_only_artifact_is_current(deploy_item: Deploy, container_name: str) -> bool:
        """
        Allow the non-build start fast-path only when the running image still
        represents the active catalog revision and its Dockerfile-owned
        ENTRYPOINT is intact.

        Older catalog deployments can survive for a long time with a rendered
        image that predates an entrypoint fix. Restarting such a container is
        not a safe no-op: it would simply bring the broken artifact back.
        """
        service = deploy_item.service
        active_revision = getattr(service, "active_revision", None)
        source_kind = str(
            getattr(service, "source_kind", "")
            or ((getattr(active_revision, "config_snapshot", None) or {}).get("source_kind") if active_revision else "")
            or ((getattr(deploy_item, "config", None) or {}).get("source_kind") if isinstance(getattr(deploy_item, "config", None), dict) else "")
            or ""
        ).strip().lower()

        if source_kind != "catalog":
            return True
        if active_revision is None:
            return False

        expected_revision = str(
            getattr(active_revision, "pk", "")
            or getattr(deploy_item, "revision_id", "")
            or ""
        ).strip()

        dockerfile = str(
            (getattr(active_revision, "build_snapshot", None) or {}).get("dockerfile")
            or ""
        )
        expected_entrypoint = None
        match = re.search(
            r"^\s*ENTRYPOINT\s+(.+?)\s*$",
            dockerfile,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if match:
            raw = match.group(1).strip()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = ["/bin/sh", "-c", raw]
            if isinstance(parsed, list):
                expected_entrypoint = [str(item) for item in parsed]

        try:
            existing = container.client.containers.get(container_name)
            image = getattr(existing, "image", None)
            image_attrs = dict(getattr(image, "attrs", None) or {})
            image_config = dict(image_attrs.get("Config") or {})
            image_labels = dict(image_config.get("Labels") or {})
            container_labels = dict(getattr(existing, "labels", None) or {})

            observed_revision = str(
                container_labels.get("io.passdeployer.revision")
                or container_labels.get("revision.id")
                or image_labels.get("io.passdeployer.revision")
                or image_labels.get("revision.id")
                or ""
            ).strip()
            if expected_revision and observed_revision != expected_revision:
                return False

            if expected_entrypoint is not None:
                actual_entrypoint = image_config.get("Entrypoint")
                if actual_entrypoint != expected_entrypoint:
                    return False
        except Exception:
            # A catalog artifact cannot safely use restart-only if its image
            # identity/config cannot be verified.
            return False

        return True

    @staticmethod
    def is_restart_only(deploy_item: Deploy, container_name: str) -> bool:
        service = deploy_item.service

        if service.deployed_at is None:
            return False

        active_revision = getattr(service, "active_revision", None)
        if active_revision is not None and active_revision.activated_at and active_revision.activated_at > service.deployed_at:
            return False

        if (
            getattr(deploy_item, "updated_file_at", None)
            and deploy_item.updated_file_at > service.deployed_at
        ):
            return False

        container = Container(container_name)
        if not container.exists():
            return False

        try:
            image_id = container.get_image_identifier()
            if not image_id:
                return False
            if not Image.check_exists(image_id):
                if not Image.check_exists(container_name) and not Image.check_exists(
                    canonical_image_ref(container_name, "latest")
                ):
                    return False
        except Exception:
            return False

        if not DeploymentHelper._restart_only_artifact_is_current(deploy_item, container_name):
            logger.info(
                "Skipping restart-only fast-path for service=%s: runtime artifact is stale or cannot be verified.",
                getattr(service, "pk", ""),
            )
            return False

        return True
