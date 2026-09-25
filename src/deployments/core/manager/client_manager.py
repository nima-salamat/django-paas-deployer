"""
deployments/core/manager/client_manager.py
------------------------------------------
Docker client singleton with timeout + retry-aware ping.

The previous implementation:
  * Created a NEW ``DockerClient`` on every ``Client()`` instantiation.
    Managers subclass ``Client``, so every ``Container(name)`` /
    ``Image(...)`` / ``Network(...)`` / ``Volume(...)`` triggered a fresh
    client + ``ping()`` — easily 5-10 client constructions per deploy.
  * Had no ``timeout`` configured, so a hung Docker daemon would block
    the deploying thread indefinitely.
  * Did not retry ``ping()`` — a single transient blip during manager
    construction aborted the entire deploy.

This module now exposes:
  * ``get_docker_client()`` — module-level lazy singleton.
  * ``Client`` — backward-compatible class.  Subclassing it (as the
    managers do) no longer creates a new docker-py client per instance;
    instead it shares the singleton.  Constructor accepts ``base_url``
    and ``timeout`` only for backward compatibility; the values are
    ignored after the first successful construction.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import docker

from deployments.common.retry import retry_with_backoff

logger = logging.getLogger(__name__)


# Defaults — can be overridden by Django settings or env vars on first init.
_DEFAULT_TIMEOUT = 60          # seconds for HTTP reads
_DEFAULT_PING_RETRIES = 3
_DEFAULT_PING_BACKOFF = 0.5


_singleton_lock = threading.Lock()
_singleton_client: Optional[docker.DockerClient] = None
_singleton_base_url: Optional[str] = None


def _resolve_base_url(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    try:
        from django.conf import settings  # type: ignore

        url = getattr(settings, "DOCKER_HOST", None)
        if url:
            return url
    except Exception:
        pass
    import os
    return os.environ.get("DOCKER_HOST") or None


def _resolve_timeout() -> int:
    try:
        from django.conf import settings  # type: ignore

        return int(getattr(settings, "DOCKER_CLIENT_TIMEOUT", _DEFAULT_TIMEOUT))
    except Exception:
        return _DEFAULT_TIMEOUT


def get_docker_client(base_url: Optional[str] = None) -> docker.DockerClient:
    """
    Return the shared ``DockerClient`` singleton.

    The first caller wins — subsequent calls ignore ``base_url`` and
    return the cached client.  This is intentional: the deployment
    subsystem talks to exactly one Docker daemon per process.
    """
    global _singleton_client, _singleton_base_url

    if _singleton_client is not None:
        return _singleton_client

    with _singleton_lock:
        # Double-checked locking.
        if _singleton_client is not None:
            return _singleton_client

        resolved_url = _resolve_base_url(base_url)
        timeout = _resolve_timeout()

        def _construct() -> docker.DockerClient:
            # docker-py accepts ``timeout`` as a top-level kwarg.
            client = (
                docker.DockerClient(base_url=resolved_url, timeout=timeout)
                if resolved_url
                else docker.from_env(timeout=timeout)
            )
            # Validate connectivity with a bounded retry.
            retry_with_backoff(
                client.ping,
                retries=_DEFAULT_PING_RETRIES,
                base_delay=_DEFAULT_PING_BACKOFF,
                max_delay=2.0,
                retry_on=(docker.errors.DockerException, OSError),
                label="docker.ping",
            )
            return client

        try:
            client = _construct()
        except Exception:
            logger.exception("Failed to create Docker client (base_url=%s).", resolved_url)
            raise

        _singleton_client = client
        _singleton_base_url = resolved_url
        logger.info(
            "Docker client initialised (base_url=%s timeout=%s).",
            resolved_url or "from_env", timeout,
        )
        return client


def reset_docker_client() -> None:
    """
    Drop the cached singleton.  Intended for tests and for recovery
    after a known daemon restart — production code should rarely call
    this.
    """
    global _singleton_client, _singleton_base_url
    with _singleton_lock:
        if _singleton_client is not None:
            try:
                _singleton_client.close()
            except Exception:
                pass
        _singleton_client = None
        _singleton_base_url = None


class Client:
    """
    Backward-compatible Docker client wrapper.

    Historically every manager (``Image``, ``Container``, ``Network``,
    ``Volume``) subclassed ``Client`` and called ``super().__init__()``
    in its own ``__init__``.  That triggered a brand-new
    ``DockerClient`` + ``ping()`` per manager instance.

    This class now delegates to the singleton.  Subclassing it is cheap
    (no I/O in the constructor) and ``self.client`` returns the shared
    client.  Existing manager code does not need to change.
    """

    def __init__(self, base_url: Optional[str] = None):
        # No per-instance client construction — share the singleton.
        # We keep the ``base_url`` parameter for signature compatibility.
        self._client = get_docker_client(base_url)

    @property
    def client(self) -> docker.DockerClient:
        """Return the shared Docker client (lazy + cached)."""
        return self._client

    def __call__(self) -> docker.DockerClient:
        """Backward-compat: old code did ``Client()()`` to fetch the client."""
        return self._client


__all__ = ["Client", "get_docker_client", "reset_docker_client"]
