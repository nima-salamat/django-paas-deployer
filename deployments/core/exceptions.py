"""
deployments/core/exceptions.py
------------------------------
Backward-compatible re-export shim.

The canonical hierarchy now lives in ``deployments/common/exceptions.py``.
This module re-exports the same names so existing imports such as
``from deployments.core.exceptions import ContainerError`` keep working.
"""

from deployments.common.exceptions import (  # noqa: F401
    DeploymentError,
    DeploymentValidationError,
    InvalidServiceStateError,
    DockerClientError,
    ImageBuildError,
    NetworkError,
    VolumeError,
    ContainerError,
    ContainerTimeoutError,
    HealthCheckError,
    RollbackError,
    CleanupError,
    DeploymentLockError,
    DeploymentCancelled,
    OrchestratorDeploymentError,
    DeploymentSecurityError,
)

__all__ = [
    "DeploymentError",
    "DeploymentValidationError",
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
    "DeploymentSecurityError",
]
