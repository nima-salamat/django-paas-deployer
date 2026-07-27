class DeploymentError(Exception):
    """Base error for deployment failures with UI-friendly context."""

    default_stage = "deployment"
    recoverable = False

    def __init__(self, message, *, stage=None, recoverable=None, details=None):
        super().__init__(message)
        self.message = str(message)
        self.stage = stage or self.default_stage
        if recoverable is not None:
            self.recoverable = recoverable
        self.details = details or {}


class DeploymentValidationError(DeploymentError):
    default_stage = "validation"


class DockerClientError(DeploymentError):
    default_stage = "docker_client"


class ImageBuildError(DeploymentError):
    default_stage = "image_build"
    recoverable = True


class NetworkError(DeploymentError):
    default_stage = "network"
    recoverable = True


class VolumeError(DeploymentError):
    default_stage = "volume"
    recoverable = True


class ContainerError(DeploymentError):
    default_stage = "container"
    recoverable = True


class HealthCheckError(DeploymentError):
    default_stage = "health_check"
    recoverable = True


class RollbackError(DeploymentError):
    default_stage = "rollback"


class CleanupError(DeploymentError):
    default_stage = "cleanup"


class DeploymentLockError(DeploymentError):
    default_stage = "deployment_lock"


class DeploymentCancelled(DeploymentError):
    default_stage = "cancelled"
    recoverable = True
