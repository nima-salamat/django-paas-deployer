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
    def _runtime_format_kwargs(
        overrides: dict | None = None,
        *,
        platform: str | None = None,
    ) -> dict:
        """
        Merge defaults with optional user overrides for Dockerfile placeholders.

        Recognised keys (all optional):
          python_version, django_python_version, node_version,
          php_version, go_version, dotnet_version, nginx_version,
          port, build_dir
        """
        from core.global_settings import config as _gcfg
        kwargs = {"MIRROR_DOCKER": _gcfg.MIRROR_DOCKER}
        kwargs.update(_gcfg.DEFAULT_RUNTIME_VERSIONS)

        # Port: platform default → global default → user override
        plat = (platform or "").lower().strip()
        port_default = _gcfg.default_ports.get(plat)
        if port_default is None:
            port_default = getattr(_gcfg, "DEFAULT_EXPOSE_PORT", 80)
        kwargs["port"] = int(port_default)

        # build_dir placeholder (SPA); generator may still refine it
        kwargs["build_dir"] = getattr(_gcfg, "DEFAULT_SPA_BUILD_DIR", "dist")

        if overrides:
            for key in DEFAULT_RUNTIME_VERSIONS:
                val = overrides.get(key)
                if val is not None and str(val).strip():
                    kwargs[key] = str(val).strip().lstrip("vV")
            if overrides.get("port") is not None and str(overrides.get("port")).strip() != "":
                try:
                    kwargs["port"] = int(overrides["port"])
                except (TypeError, ValueError):
                    pass
            if overrides.get("build_dir"):
                kwargs["build_dir"] = str(overrides["build_dir"]).strip().lstrip("./").rstrip("/")
        return kwargs

    @staticmethod
    def get_dockerfile_text(
        platform: str,
        *,
        version_overrides: dict | None = None,
    ) -> str | None:
        """
        Return the Dockerfile template for ``platform`` with placeholders
        substituted (versions, port, build_dir, mirror).

        Still leaves placeholders that the generator must fill later
        (e.g. Django ``{module}``).

        Pass overrides from Deploy.config::
          {"python_version": "3.12", "node_version": "22", "port": 8080}
        """
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
            # Leave unknown placeholders (e.g. {module}) for DockerfileGenerator
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


