"""
deployments/common/exceptions.py
--------------------------------
Unified exception hierarchy for the deployment subsystem.

Every Celery-specific and core error is a DeploymentError subclass so
callers can catch one family without silent misses.
"""

from __future__ import annotations

from typing import Any, Optional


class DeploymentError(Exception):
    """Base for all deployment failures."""

    recoverable: bool = False
    stage: str = "deployment"

    def __init__(
        self,
        message: str = "",
        *,
        stage: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        recoverable: Optional[bool] = None,
    ):
        self.message = message or str(self)
        if stage is not None:
            self.stage = stage
        self.details = details or {}
        if recoverable is not None:
            self.recoverable = recoverable
        super().__init__(self.message)


class DeploymentValidationError(DeploymentError):
    recoverable = False
    stage = "validation"


class DeploymentSecurityError(DeploymentError):
    """Path traversal, unsafe bind, shell injection, etc. Never retry."""
    recoverable = False
    stage = "security"


class InvalidServiceStateError(DeploymentError):
    recoverable = False
    stage = "state"


class DockerClientError(DeploymentError):
    recoverable = True
    stage = "docker"


class ImageBuildError(DeploymentError):
    recoverable = False
    stage = "image_build"


class NetworkError(DeploymentError):
    recoverable = False
    stage = "network"


class VolumeError(DeploymentError):
    recoverable = False
    stage = "volume"


class ContainerError(DeploymentError):
    recoverable = False
    stage = "container"


class ContainerTimeoutError(DeploymentError):
    recoverable = True
    stage = "timeout"


class HealthCheckError(DeploymentError):
    recoverable = False
    stage = "health_check"


class RollbackError(DeploymentError):
    recoverable = False
    stage = "rollback"


class CleanupError(DeploymentError):
    recoverable = False
    stage = "cleanup"


class DeploymentLockError(DeploymentError):
    recoverable = False
    stage = "lock"


class DeploymentCancelled(DeploymentError):
    recoverable = False
    stage = "cancelled"


class OrchestratorDeploymentError(DeploymentError):
    recoverable = False
    stage = "orchestrator"


__all__ = [
    "DeploymentError",
    "DeploymentValidationError",
    "DeploymentSecurityError",
    "InvalidServiceStateError",
    "DockerClientError",
    "ImageBuildError",
    "NetworkError",
    "VolumeError",
    "ContainerError",
    "ContainerTimeoutError",
    "HealthCheckError",
    "RollbackError",
    "CleanupError",
    "DeploymentLockError",
    "DeploymentCancelled",
    "OrchestratorDeploymentError",
]
