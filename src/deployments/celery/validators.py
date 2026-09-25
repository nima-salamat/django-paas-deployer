"""
deployments/celery/validators.py
--------------------------------
Business-rule validation for deployments.

Key changes vs. legacy:
  * Uses the unified ``deployments.common.parse_config`` (was a local
    duplicate of the same JSON-decoding logic).
  * Uses the unified ``DeploymentValidationError`` from
    ``deployments.common.exceptions``.
"""

from __future__ import annotations

from deploy.models import Deploy  # type: ignore
from deployments.core.db_deployer import DB_PLATFORMS, validate_db_config
from deployments.common import parse_config
from deployments.common.exceptions import DeploymentValidationError


class DeploymentValidator:
    """Validates deployment business rules before deployment starts."""

    @classmethod
    def _platform(cls, deploy_item: Deploy) -> str:
        cfg = parse_config(getattr(deploy_item, "config", None))
        p = cfg.get("platform")
        if p:
            return str(p).lower().strip()
        plan = getattr(getattr(deploy_item, "service", None), "plan", None)
        if plan and getattr(plan, "platform", None):
            return str(plan.platform).lower().strip()
        return "docker"

    @classmethod
    def is_db_deploy(cls, deploy_item: Deploy) -> bool:
        return cls._platform(deploy_item) in DB_PLATFORMS

    @classmethod
    def validate_for_deploy(
        cls,
        deploy_item: Deploy,
        dockerfile_text: str | None,
    ) -> None:
        service = deploy_item.service

        if service is None:
            raise DeploymentValidationError(
                "Deployment has no associated service."
            )

        if service.network_id is None:
            raise DeploymentValidationError(
                "Service must have a private network before deployment."
            )

        if not service.plan_id:
            raise DeploymentValidationError(
                "Service must have a plan before deployment."
            )

        platform = cls._platform(deploy_item)
        cfg = parse_config(getattr(deploy_item, "config", None))

        # ------------------------------------------------------------------
        # DB platforms: credentials only — NO zip, NO dockerfile template
        # ------------------------------------------------------------------
        if platform in DB_PLATFORMS:
            if not cfg.get("platform"):
                cfg = {**cfg, "platform": platform}
            errors = validate_db_config(platform, cfg)
            if errors:
                raise DeploymentValidationError(
                    "DB config validation failed: " + "; ".join(errors)
                )
            return

        # ------------------------------------------------------------------
        # App platforms: zip + dockerfile required
        # ------------------------------------------------------------------
        if not deploy_item.zip_file:
            raise DeploymentValidationError(
                "Missing zip file for deployment."
            )

        if not dockerfile_text:
            raise DeploymentValidationError(
                f"Missing dockerfile configuration for platform: {platform}"
            )

        # Soft checks for Celery flags (do not fail deploy; warn via message only)
        if cfg.get("celery") and platform not in ("django", "flask", "python"):
            # Celery supervisord injection is only implemented for Python family
            raise DeploymentValidationError(
                f"Celery is only supported for Django/Flask/Python platforms "
                f"(got '{platform}')."
            )
