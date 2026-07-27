from deploy.models import Deploy
from .exceptions import DeploymentValidationError


class DeploymentValidator:
    """Validates deployment business rules before structural actions run."""

    @classmethod
    def validate_for_deploy(cls, deploy_item: Deploy, dockerfile_text: str | None) -> None:
        if not deploy_item.zip_file:
            raise DeploymentValidationError("Missing zip file for deployment.")

        if getattr(deploy_item.service, 'selected_deploy_at', None) is None:
            raise DeploymentValidationError("Service selected_deploy_at is not set.")

        if deploy_item.service.selected_deploy_id != deploy_item.id:
            raise DeploymentValidationError("Deploy item is not the currently selected deployment for this service.")

        if deploy_item.service.network_id is None:
            raise DeploymentValidationError("Service must have a private network before deployment.")

        if not dockerfile_text:
            raise DeploymentValidationError(
                f"Missing dockerfile configuration for platform: {deploy_item.service.plan.platform}"
            )
