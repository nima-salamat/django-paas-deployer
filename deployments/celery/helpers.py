from dataclasses import dataclass
from deploy.models import Deploy
from core.global_settings.config import Config
from deployments.core.manager.container_manager import Container


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

    # Platform id → Config attribute (when names differ)
    _DOCKERFILE_ALIASES = {
        "vuejs": "vue",
        "vue": "vue",
        "statichtmlcss": "static",
        "static": "static",
        "html": "static",
        "fastapi": "python",  # share python template; generator specialises
    }

    @staticmethod
    def _runtime_format_kwargs(overrides: dict | None = None) -> dict:
        """
        Merge DEFAULT_RUNTIME_VERSIONS with optional user overrides.

        Recognised override keys (all optional strings):
          python_version, django_python_version, node_version,
          php_version, go_version, dotnet_version, nginx_version
        """
        from core.global_settings.config import (
            DEFAULT_RUNTIME_VERSIONS,
            MIRROR_DOCKER,
        )
        kwargs = {"MIRROR_DOCKER": MIRROR_DOCKER}
        kwargs.update(DEFAULT_RUNTIME_VERSIONS)
        if overrides:
            for key in DEFAULT_RUNTIME_VERSIONS:
                val = overrides.get(key)
                if val is not None and str(val).strip():
                    # strip leading 'v' if user passes "v20"
                    kwargs[key] = str(val).strip().lstrip("vV")
        return kwargs

    @staticmethod
    def get_dockerfile_text(
        platform: str,
        *,
        version_overrides: dict | None = None,
    ) -> str | None:
        """
        Return the Dockerfile template for ``platform`` with runtime version
        placeholders already substituted.

        Pass ``version_overrides`` from Deploy.config to let the user pick
        e.g. ``{"python_version": "3.12", "node_version": "22"}``.
        """
        key = (platform or "").lower().strip()
        attr = DeploymentHelper._DOCKERFILE_ALIASES.get(key, key)
        raw = getattr(Config, attr, None) or getattr(Config, key, None)
        if not raw:
            return None
        fmt = DeploymentHelper._runtime_format_kwargs(version_overrides)
        try:
            return raw.format(**fmt)
        except KeyError:
            # Template may still contain other placeholders (e.g. {module}
            # for Django) that DockerfileGenerator fills later.  Only fill
            # the keys we know about.
            out = raw
            for k, v in fmt.items():
                out = out.replace("{" + k + "}", str(v))
            return out

    @staticmethod
    def is_restart_only(deploy_item: Deploy, container_name: str) -> bool:
        service = deploy_item.service
        
        if service.deployed_at is None:
            return False

        if service.selected_deploy_at and service.selected_deploy_at > service.deployed_at:
            return False

        if deploy_item.updated_file_at and deploy_item.updated_file_at > service.deployed_at:
            return False

        return Container(container_name).exists()

