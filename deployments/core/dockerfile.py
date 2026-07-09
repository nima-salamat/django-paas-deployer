from .entrypoints import require_django_entrypoint
from .exceptions import DeploymentValidationError


class DockerfileGenerator:
    """Render platform Dockerfiles from uploaded project context."""

    def render(self, *, platform: str, dockerfile_template: str, tar_stream, logger=None) -> str:
        if not dockerfile_template:
            raise DeploymentValidationError("Dockerfile template is required.", stage="dockerfile_generation")

        if platform != "django":
            return dockerfile_template

        if logger:
            logger.info("entrypoint_detection", "Detecting Django ASGI/WSGI entrypoint.", progress=12)

        entrypoint = require_django_entrypoint(tar_stream)
        module = entrypoint["module"]

        try:
            rendered = dockerfile_template.format(module)
        except Exception as exc:
            raise DeploymentValidationError(
                "Django Dockerfile template could not be rendered.",
                stage="dockerfile_generation",
                details={"module": module},
            ) from exc

        if logger:
            logger.info(
                "dockerfile_generation",
                "Django Dockerfile rendered.",
                progress=15,
                details={"entrypoint_type": entrypoint["type"], "module": module},
            )

        return rendered
