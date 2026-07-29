from deploy.models import Deploy
from .exceptions import DeploymentValidationError


class DeploymentValidator:
    """Validates deployment business rules before deployment starts."""

    @classmethod
    def validate_for_deploy(
        cls,
        deploy_item: Deploy,
        dockerfile_text: str | None,
    ) -> None:
        if not deploy_item.zip_file:
            raise DeploymentValidationError(
                "Missing zip file for deployment."
            )

        service = deploy_item.service

        if service is None:
            raise DeploymentValidationError(
                "Deployment has no associated service."
            )

        # network is nullable on the model; business rule still requires it
        if service.network_id is None:
            raise DeploymentValidationError(
                "Service must have a private network before deployment."
            )

        # plan is non-nullable on the model; guard kept for safety
        if not service.plan_id:
            raise DeploymentValidationError(
                "Service must have a plan before deployment."
            )

        if not dockerfile_text:
            platform = getattr(getattr(service, "plan", None), "platform", "unknown")
            raise DeploymentValidationError(
                f"Missing dockerfile configuration for platform: {platform}"
            )