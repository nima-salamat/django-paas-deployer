from dataclasses import dataclass

from deploy.models import Deploy
from core.global_settings.config import Config
from deployments.core.manager.container_manager import Container
from deployments.core.manager.image_manager import Image


@dataclass(frozen=True)
class MockOrchestratorResult:
    """Value object matching the Orchestrator result shape for local execution paths."""

    success: bool
    stage: str
    message: str
    error: str = ""
    rollback_performed: bool = False
    status: str = ""


class DeploymentHelper:
    """Utility class for evaluating deployment conditions and configurations."""

    _DOCKERFILE_ALIASES = {
        "vuejs": "vue",
        "vue": "vue",
        "statichtmlcss": "static",
        "static": "static",
        "html": "static",
        "fastapi": "python",
    }

    @staticmethod
    def _runtime_format_kwargs(
        overrides: dict | None = None,
        *,
        platform: str | None = None,
    ) -> dict:
        from core.global_settings import config as _gcfg

        kwargs = {"MIRROR_DOCKER": getattr(_gcfg, "MIRROR_DOCKER", "docker.io")}
        versions = getattr(_gcfg, "DEFAULT_RUNTIME_VERSIONS", None) or {
            "python_version": "3.11",
            "django_python_version": "3.10",
            "node_version": "20",
            "php_version": "8.2",
            "go_version": "1.21",
            "dotnet_version": "6.0",
            "nginx_version": "alpine",
        }
        kwargs.update(versions)

        # Port: platform default
        try:
            from core.global_settings.config import default_ports, DEFAULT_EXPOSE_PORT

            p = (platform or "").lower().strip()
            port = default_ports.get(p)
            if port is None:
                port = DEFAULT_EXPOSE_PORT
            kwargs["port"] = port
        except Exception:
            kwargs.setdefault("port", 80)

        kwargs.setdefault("build_dir", "dist")

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
        """
        True only when we can safely restart an *existing* container that
        still has its image. If the container or image is missing, return
        False so the orchestrator does a full rebuild from the zip.
        """
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

        # Image must still be present; otherwise restart would fail and
        # the user expects a rebuild from the existing zip.
        try:
            image_id = container.get_image_identifier()
            if not image_id:
                return False
            # Prefer checking by id; also try common name:tag patterns
            if not Image.check_exists(image_id):
                # Fallback: any tag under container name
                if not Image.check_exists(container_name) and not Image.check_exists(
                    f"{container_name}:latest"
                ):
                    return False
        except Exception:
            # On any inspect error treat as missing → full rebuild
            return False

        return True
