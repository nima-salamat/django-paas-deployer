from .entrypoints import require_django_entrypoint
from .exceptions import DeploymentValidationError

from core.global_settings.config import MIRROR_DOCKER


class DockerfileGenerator:

    def render(
        self,
        *,
        platform: str,
        dockerfile_template: str,
        tar_stream,
        logger=None,
    ) -> str:

        # ---------------------------------------------------------
        # Validate template
        # ---------------------------------------------------------
        if not dockerfile_template:
            raise DeploymentValidationError(
                "Dockerfile template is required.",
                stage="dockerfile_generation",
            )

        # ---------------------------------------------------------
        # Non-Django platforms
        # ---------------------------------------------------------
        if platform != "django":
            return dockerfile_template

        # ---------------------------------------------------------
        # Detect Django ASGI / WSGI entrypoint
        # ---------------------------------------------------------
        if logger:
            logger.info(
                "entrypoint_detection",
                "Detecting Django ASGI/WSGI entrypoint.",
                progress=12,
            )

        entrypoint = require_django_entrypoint(tar_stream)

        module = entrypoint["module"]
        entrypoint_type = entrypoint["type"]

        # ---------------------------------------------------------
        # Render Dockerfile
        # ---------------------------------------------------------
        try:
            rendered = dockerfile_template.format(
                module=module,
                MIRROR_DOCKER=MIRROR_DOCKER,
            )

        except KeyError as exc:
            missing_key = exc.args[0] if exc.args else "unknown"

            if logger:
                logger.error(
                    "dockerfile_generation",
                    "Django Dockerfile template contains an unknown placeholder.",
                    progress=15,
                    details={
                        "module": module,
                        "missing_placeholder": missing_key,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            raise DeploymentValidationError(
                f"Django Dockerfile template contains an unknown placeholder: {missing_key}",
                stage="dockerfile_generation",
                details={
                    "module": module,
                    "missing_placeholder": missing_key,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc

        except (IndexError, ValueError) as exc:

            if logger:
                logger.error(
                    "dockerfile_generation",
                    "Django Dockerfile template formatting failed.",
                    progress=15,
                    details={
                        "module": module,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            raise DeploymentValidationError(
                "Django Dockerfile template could not be rendered.",
                stage="dockerfile_generation",
                details={
                    "module": module,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc

        except Exception as exc:

            if logger:
                logger.error(
                    "dockerfile_generation",
                    "Unexpected error while rendering Django Dockerfile.",
                    progress=15,
                    details={
                        "module": module,
                        "entrypoint_type": entrypoint_type,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            raise DeploymentValidationError(
                "Django Dockerfile template could not be rendered.",
                stage="dockerfile_generation",
                details={
                    "module": module,
                    "entrypoint_type": entrypoint_type,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc

        # ---------------------------------------------------------
        # Success
        # ---------------------------------------------------------
        if logger:
            logger.info(
                "dockerfile_generation",
                "Django Dockerfile rendered.",
                progress=15,
                details={
                    "entrypoint_type": entrypoint_type,
                    "module": module,
                    "mirror": MIRROR_DOCKER,
                },
            )

        return rendered
