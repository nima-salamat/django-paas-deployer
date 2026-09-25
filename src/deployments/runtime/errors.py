"""Errors crossing the runtime contract boundary."""

from __future__ import annotations

from typing import Any, Mapping

from deployments.common.exceptions import DeploymentError


class RuntimeOperationError(DeploymentError):
    """A normalized runtime failure safe for application-layer handling."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "runtime_operation_failed",
        recoverable: bool = False,
        category: str = "runtime_error",
        details: Mapping[str, Any] | None = None,
        user_message: str | None = None,
    ) -> None:
        super().__init__(
            message,
            stage="runtime",
            recoverable=bool(recoverable),
            category=category,
            code=code,
            details=dict(details or {}),
            user_message=user_message or message,
        )


class RuntimeUnavailableError(RuntimeOperationError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "runtime_unavailable")
        kwargs.setdefault("recoverable", True)
        kwargs.setdefault("category", "runtime_availability")
        super().__init__(message, **kwargs)


class RuntimeUnsupportedError(RuntimeOperationError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "runtime_capability_unsupported")
        kwargs.setdefault("recoverable", False)
        kwargs.setdefault("category", "runtime_capability")
        super().__init__(message, **kwargs)
