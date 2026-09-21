"""
deployments/common/retry.py
---------------------------
Tiny, dependency-free retry helpers tuned for Docker / infrastructure calls.

We deliberately do NOT use ``tenacity`` or similar libraries because:
  * The deployment subsystem must be installable in a constrained Django
    environment where adding deps is a heavy process.
  * Our retry needs are narrow: a handful of Docker calls, with bounded
    attempts and exponential backoff + jitter.

All helpers raise the original exception once attempts are exhausted —
they never swallow it.  Callers are expected to wrap with their own
exception translation (e.g. DockerException -> ContainerError).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Iterable, Tuple, Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    skip_on: Tuple[Type[BaseException], ...] = (),
    label: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Call ``func(*args, **kwargs)`` with exponential backoff + jitter.

    Parameters
    ----------
    retries
        Maximum number of retries (so up to ``retries + 1`` total attempts).
    base_delay, max_delay
        Backoff is ``min(max_delay, base_delay * 2**attempt)`` plus up to
        25% jitter.
    retry_on
        Exception types that should trigger a retry.
    skip_on
        Exception types that should be re-raised immediately, even if they
        are a subclass of something in ``retry_on``.  Use this to exempt
        permanent errors (e.g. ``NotFound``) from retry.
    label
        Human-readable label used in log lines.
    """
    if not retry_on:
        return func(*args, **kwargs)

    attempt = 0
    last_exc: BaseException | None = None
    while attempt <= retries:
        try:
            return func(*args, **kwargs)
        except skip_on:
            raise
        except retry_on as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay = delay + random.uniform(0, delay * 0.25)
            logger.warning(
                "retry[%s] attempt %d/%d failed: %s; sleeping %.2fs",
                label or func.__name__, attempt + 1, retries + 1, exc, delay,
            )
            time.sleep(delay)
            attempt += 1
    assert last_exc is not None
    raise last_exc


def is_retryable_exception(
    exc: BaseException,
    *,
    recoverable_types: Iterable[Type[BaseException]] = (),
    permanent_types: Iterable[Type[BaseException]] = (),
    transient_markers: Iterable[str] = (),
) -> bool:
    """
    Decide whether ``exc`` is worth retrying.

    Rules (in order):
      1. If ``exc`` is an instance of any ``permanent_types`` -> False.
      2. If ``exc`` has a ``recoverable`` attribute that is explicitly
         False -> False.
      3. If ``exc`` is an instance of any ``recoverable_types`` -> True.
      4. If the exception class name or message contains any
         ``transient_markers`` substring (case-insensitive) -> True.
      5. Otherwise -> False.

    This replaces the brittle text-matching ``_is_retryable`` in
    ``celery/tasks.py`` while preserving its behaviour for backward
    compatibility.
    """
    permanent_types = tuple(permanent_types)
    if permanent_types and isinstance(exc, permanent_types):
        return False

    recoverable_attr = getattr(exc, "recoverable", None)
    if recoverable_attr is False:
        return False

    recoverable_types = tuple(recoverable_types)
    if recoverable_types and isinstance(exc, recoverable_types):
        return True

    name = type(exc).__name__.lower()
    text = str(exc).lower()
    for marker in transient_markers:
        m = marker.lower()
        if m in name or m in text:
            return True
    return False


__all__ = ["retry_with_backoff", "is_retryable_exception"]
