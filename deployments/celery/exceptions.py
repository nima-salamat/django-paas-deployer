"""
deployments/celery/exceptions.py
--------------------------------
Backward-compatible re-export shim.

Historically this module defined its OWN hierarchy rooted at
``CeleryDeploymentError`` (which was NOT a ``DeploymentError`` subclass)
and even defined a class named ``DeploymentValidationError`` that
collided with the one in ``deployments/core/exceptions.py``.  Code that
caught one family would silently miss the other.

The unified hierarchy now lives in ``deployments/common/exceptions.py``
where every Celery-specific error IS a ``DeploymentError``.  This module
keeps the historical names as aliases so existing call sites continue
to import from here.
"""

from deployments.common.exceptions import (  # noqa: F401
    DeploymentError as CeleryDeploymentError,
    DeploymentValidationError,
    InvalidServiceStateError,
    ContainerTimeoutError,
    OrchestratorDeploymentError,
    ContainerError,
    ImageBuildError,
    NetworkError,
    VolumeError,
    HealthCheckError,
    RollbackError,
    CleanupError,
    DeploymentLockError,
    DeploymentCancelled,
    DeploymentSecurityError,
)

__all__ = [
    "CeleryDeploymentError",
    "DeploymentValidationError",
    "InvalidServiceStateError",
    "ContainerTimeoutError",
    "OrchestratorDeploymentError",
    "ContainerError",
    "ImageBuildError",
    "NetworkError",
    "VolumeError",
    "HealthCheckError",
    "RollbackError",
    "CleanupError",
    "DeploymentLockError",
    "DeploymentCancelled",
    "DeploymentSecurityError",
]
