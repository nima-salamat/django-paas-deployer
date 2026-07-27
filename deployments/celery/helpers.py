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

    @staticmethod
    def get_dockerfile_text(platform: str) -> str | None:
        return getattr(Config, platform, None)

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
