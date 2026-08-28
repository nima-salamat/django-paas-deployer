"""deployments/celery/helpers.py — mirrors + versions from DB settings."""
from dataclasses import dataclass

from deploy.models import Deploy
from core.global_settings.config import Config
from deployments.core.manager.container_manager import Container
from deployments.core.manager.image_manager import Image


@dataclass(frozen=True)
class MockOrchestratorResult:
    success: bool
    stage: str
    message: str
    error: str = ""
    rollback_performed: bool = False
    status: str = ""


class DeploymentHelper:
    _DOCKERFILE_ALIASES = {
        "vuejs": "vue",
        "vue": "vue",
        "statichtmlcss": "static",
        "static": "static",
        "html": "static",
        "fastapi": "python",
        # PHP family — Laravel/Symfony/etc. share the php Apache template;
        # framework-specific bootstrap is injected later in dockerfile.py.
        "laravel": "php",
        "symfony": "php",
        "codeigniter": "php",
        "lumen": "php",
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

        kwargs = {
            "MIRROR_DOCKER": mirror_docker,
            "MIRROR_PYTHON": mirror_python,
            "MIRROR_NPM": mirror_npm,
            "MIRROR_APT": mirror_apt or "http://deb.debian.org/debian/",
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
    def get_dockerfile_text(
        platform: str,
        *,
        version_overrides: dict | None = None,
    ) -> str | None:
        key = (platform or "").lower().strip()
        attr = DeploymentHelper._DOCKERFILE_ALIASES.get(key, key)

        # 1) DB template if present
        raw = None
        try:
            from core import settings_service as svc

            raw = svc.dockerfile_template(attr) or svc.dockerfile_template(key)
        except Exception:
            pass

        # 2) Code Config class
        if not raw:
            raw = getattr(Config, attr, None) or getattr(Config, key, None)
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
    def is_restart_only(deploy_item: Deploy, container_name: str) -> bool:
        service = deploy_item.service

        if service.deployed_at is None:
            return False

        if (
            service.selected_deploy_at
            and service.selected_deploy_at > service.deployed_at
        ):
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
                    f"{container_name}:latest"
                ):
                    return False
        except Exception:
            return False

        return True
