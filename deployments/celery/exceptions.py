class CeleryDeploymentError(Exception):
    """Base exception for all deployment-related errors in Celery."""
    pass


class InvalidServiceStateError(CeleryDeploymentError):
    """Raised when the service is in an unexpected state."""
    pass


class DeploymentValidationError(CeleryDeploymentError):
    """Raised when the deployment parameters fail business validation."""
    pass


class ContainerTimeoutError(CeleryDeploymentError):
    """Raised when a container fails to reach the expected state within the timeout."""
    pass


class OrchestratorDeploymentError(CeleryDeploymentError):
    """Raised when the underlying DeploymentOrchestrator returns errors."""
    pass