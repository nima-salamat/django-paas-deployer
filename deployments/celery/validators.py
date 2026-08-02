import json

from deploy.models import Deploy
from deployments.core.db_deployer import DB_PLATFORMS, validate_db_config
from .exceptions import DeploymentValidationError


def _parse_config(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except Exception:
            pass
    return {}


class DeploymentValidator:
    """Validates deployment business rules before deployment starts."""

    @classmethod
    def _platform(cls, deploy_item: Deploy) -> str:
        cfg = _parse_config(getattr(deploy_item, "config", None))
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

        # network is nullable on the model; business rule still requires it
        if service.network_id is None:
            raise DeploymentValidationError(
                "Service must have a private network before deployment."
            )

        if not service.plan_id:
            raise DeploymentValidationError(
                "Service must have a plan before deployment."
            )

        platform = cls._platform(deploy_item)
        cfg = _parse_config(getattr(deploy_item, "config", None))

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
