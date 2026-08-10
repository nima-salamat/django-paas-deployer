"""
deployments/common/exceptions.py
--------------------------------
Unified exception hierarchy for the entire deployment subsystem.

Previously the codebase had TWO parallel hierarchies:
  * deployments/core/exceptions.py    -> DeploymentError + subclasses
  * deployments/celery/exceptions.py  -> CeleryDeploymentError + subclasses
                                         (NOT a DeploymentError subclass)

Both modules even defined a class named ``DeploymentValidationError``
referring to DIFFERENT behaviour, so ``except DeploymentValidationError``
silently caught the wrong family depending on import order.  This file
unifies them under a single base, preserves the historical names as
aliases, and lets old call sites keep importing from their original
modules via re-export shims.

Design rules
------------
* Every exception carries:
    - ``message``: short, user-visible diagnostic
    - ``stage``: lifecycle stage identifier (used by sinks + logs)
    - ``recoverable``: hint for retry logic (True = transient; False = permanent)
    - ``details``: structured dict for sinks / observability
* Subclasses set ``default_stage`` and ``recoverable`` as class attributes;
  callers may override per-instance via constructor kwargs.
* ``InvalidServiceStateError`` and ``DeploymentCancelled`` are NOT
  ``DeploymentError`` subclasses semantically, but they ARE in this module
  to keep a single inheritance root for ``except`` clauses.
"""

from __future__ import annotations

from typing import Any


class DeploymentError(Exception):
    """Base error for all deployment failures."""

    default_stage = "deployment"
    recoverable = False

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        recoverable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.stage = stage or self.default_stage
        if recoverable is not None:
            self.recoverable = recoverable
        self.details = details or {}


# ---------------------------------------------------------------------------
# Validation / business-rule errors (permanent)
# ---------------------------------------------------------------------------

class DeploymentValidationError(DeploymentError):
    default_stage = "validation"
    recoverable = False


class InvalidServiceStateError(DeploymentError):
    """
    Service or Deploy is in a state that does not allow the requested
    operation.  This is permanent for the current attempt — the caller
    should NOT retry.
    """
    default_stage = "service_state"
    recoverable = False


# ---------------------------------------------------------------------------
# Infrastructure errors (mostly transient)
# ---------------------------------------------------------------------------

class DockerClientError(DeploymentError):
    default_stage = "docker_client"
    recoverable = True


class ImageBuildError(DeploymentError):
    default_stage = "image_build"
    # Build failures are usually permanent (bad Dockerfile), but a small
    # subset (network mirror blip, daemon restart) is transient.  We keep
    # recoverable=True so the orchestrator's retry wrapper can attempt
    # one bounded retry; the retry policy in tasks.py decides explicitly.
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


class ContainerTimeoutError(DeploymentError):
    default_stage = "container_timeout"
    recoverable = True


class HealthCheckError(DeploymentError):
    default_stage = "health_check"
    recoverable = True


# ---------------------------------------------------------------------------
# Lifecycle errors
# ---------------------------------------------------------------------------

class RollbackError(DeploymentError):
    """Rollback itself failed — service may be left without a container."""
    default_stage = "rollback"
    recoverable = False


class CleanupError(DeploymentError):
    default_stage = "cleanup"
    recoverable = False


class DeploymentLockError(DeploymentError):
    """Could not acquire or hold a deployment lock."""
    default_stage = "deployment_lock"
    recoverable = True


class DeploymentCancelled(DeploymentError):
    """User requested cancellation.  Not a failure per se."""
    default_stage = "cancelled"
    recoverable = False


class OrchestratorDeploymentError(DeploymentError):
    """The orchestrator returned a failed DeploymentResult."""
    default_stage = "orchestrator"
    recoverable = False


# ---------------------------------------------------------------------------
# Security errors (always permanent)
# ---------------------------------------------------------------------------

class DeploymentSecurityError(DeploymentValidationError):
    """A user-supplied input failed a security check (path traversal,
    command-injection pattern, forbidden host path, etc.)."""
    default_stage = "security"
    recoverable = False


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
