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
    """Base error for all deployment failures.

    ``message`` is kept backward-compatible as the user-facing message.
    ``technical_message`` and the structured code/category fields are for
    diagnostics and event consumers; they must not be shown directly to
    end users unless explicitly intended by a subclass/caller.
    """

    default_stage = "deployment"
    default_code = "DEPLOYMENT_ERROR"
    default_category = "deployment_error"
    default_user_message: str | None = None
    recoverable = False

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        recoverable: bool | None = None,
        details: dict[str, Any] | None = None,
        user_message: str | None = None,
        technical_message: str | None = None,
        code: str | None = None,
        category: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.user_message = str(user_message or self.default_user_message or message)
        self.technical_message = str(technical_message or message)
        self.stage = stage or self.default_stage
        if recoverable is not None:
            self.recoverable = recoverable
        self.code = str(code or self.default_code)
        self.category = str(category or self.default_category)
        self.details = dict(details or {})


class InternalPlatformError(DeploymentError):
    """Unexpected platform/programming failure that is not user-recoverable."""

    default_stage = "deployment"
    default_code = "INTERNAL_PLATFORM_ERROR"
    default_category = "internal_platform_error"
    recoverable = False

    def __init__(
        self,
        message: str = "Deployment failed because of an internal platform error.",
        *,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
        user_message: str | None = None,
        technical_message: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            stage=stage,
            recoverable=False,
            details=details,
            user_message=user_message
            or "Deployment failed during deployment preparation. "
               "The deployment platform encountered an internal error before the build started.",
            technical_message=technical_message or message,
            code=code,
            category="internal_platform_error",
        )


def to_deployment_error(
    exception: Exception,
    *,
    stage: str | None = None,
    user_message: str | None = None,
) -> DeploymentError:
    """Translate an arbitrary exception into the deployment error contract.

    Existing ``DeploymentError`` instances keep their classification. Plain
    Python exceptions become non-recoverable internal platform failures, so
    programming mistakes such as ``NameError`` are never retried as transient
    infrastructure failures and never become raw user-facing messages.
    """
    if isinstance(exception, DeploymentError):
        return exception

    resolved_stage = stage or "deployment"
    return InternalPlatformError(
        stage=resolved_stage,
        technical_message=str(exception) or type(exception).__name__,
        user_message=user_message,
        details={
            "exception_type": type(exception).__name__,
            "technical_message": str(exception) or type(exception).__name__,
        },
    )


# ---------------------------------------------------------------------------
# Validation / business-rule errors (permanent)
# ---------------------------------------------------------------------------

class DeploymentValidationError(DeploymentError):
    default_stage = "validation"
    default_code = "DEPLOYMENT_VALIDATION_ERROR"
    default_category = "validation_error"
    default_user_message = "Deployment configuration is invalid. Review the validation details and correct the deployment settings or project configuration."
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
    default_code = "DOCKER_CLIENT_ERROR"
    default_category = "docker_error"
    default_user_message = "The deployment platform could not communicate with Docker. Retry the deployment; if the problem persists, contact the platform administrator."
    recoverable = True


class ImageBuildError(DeploymentError):
    default_stage = "image_build"
    default_code = "IMAGE_BUILD_ERROR"
    default_category = "build_error"
    default_user_message = "The application image could not be built. Review the build log for the first failing command and its output."
    # A Dockerfile/dependency build failure is deterministic by default.
    # Callers that can positively identify a transient infrastructure issue
    # may override recoverable=True on the instance.
    recoverable = False


class NetworkError(DeploymentError):
    default_stage = "network"
    default_code = "NETWORK_ERROR"
    default_category = "network_error"
    default_user_message = "The deployment could not prepare the required Docker network. Retry the deployment; persistent failures may require platform administrator action."
    recoverable = True


class VolumeError(DeploymentError):
    default_stage = "volume"
    default_code = "VOLUME_ERROR"
    default_category = "volume_error"
    default_user_message = "The deployment could not prepare the required storage volume. Check the deployment storage configuration and try again."
    recoverable = True


class ContainerError(DeploymentError):
    default_stage = "container"
    default_code = "CONTAINER_ERROR"
    default_category = "runtime_start_error"
    default_user_message = "The application container could not be created or started. Review the deployment logs for the Docker error and application startup output."
    recoverable = True


class ContainerTimeoutError(DeploymentError):
    default_stage = "container_timeout"
    default_code = "CONTAINER_TIMEOUT"
    default_category = "timeout"
    default_user_message = "The application container did not start within the allowed time. Check application startup logs and runtime configuration."
    recoverable = True


class HealthCheckError(DeploymentError):
    default_stage = "health_check"
    default_code = "HEALTH_CHECK_ERROR"
    default_category = "health_check_error"
    default_user_message = "The application container started but did not become ready before the health-check timeout. Check application startup logs and the configured health check or port."
    recoverable = True


# ---------------------------------------------------------------------------
# Lifecycle errors
# ---------------------------------------------------------------------------

class RollbackError(DeploymentError):
    """Rollback itself failed — service may be left without a container."""
    default_stage = "rollback"
    default_code = "ROLLBACK_ERROR"
    default_category = "rollback_error"
    default_user_message = "The deployment failed and the platform could not fully restore the previous version. Operator intervention may be required."
    recoverable = False


class CleanupError(DeploymentError):
    default_stage = "cleanup"
    default_code = "CLEANUP_ERROR"
    default_category = "cleanup_error"
    default_user_message = "The deployment failed while cleaning up temporary resources. The previous application state was not necessarily affected."
    recoverable = False


class DeploymentLockError(DeploymentError):
    """Could not acquire or hold a deployment lock."""
    default_stage = "deployment_lock"
    default_code = "DEPLOYMENT_LOCK_ERROR"
    default_category = "infrastructure_error"
    default_user_message = "The deployment could not acquire the service deployment lock. Another deployment may still be running; try again shortly."
    recoverable = True


class DeploymentCancelled(DeploymentError):
    """User requested cancellation.  Not a failure per se."""
    default_stage = "cancelled"
    recoverable = False


class OrchestratorDeploymentError(DeploymentError):
    """The orchestrator returned a failed DeploymentResult."""
    default_stage = "orchestrator"
    default_code = "DEPLOYMENT_ORCHESTRATION_ERROR"
    default_category = "deployment_error"
    default_user_message = "Deployment failed during orchestration. Review the deployment stage and technical diagnostics for the underlying cause."
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
    "InternalPlatformError",
    "to_deployment_error",
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
