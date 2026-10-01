"""
deployments/core/manager/client_manager.py
------------------------------------------
Runtime-aware Docker client pool with timeout + retry-aware ping.

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
  * ``get_docker_client()`` — keyed lazy client pool.
  * ``Client`` — backward-compatible class.  Subclassing it (as the
    managers do) no longer creates a new docker-py client per instance;
    instead it shares the singleton.  Constructor accepts ``base_url``
    and ``timeout`` only for backward compatibility; the values are
    ignored after the first successful construction.
"""

from __future__ import annotations

import logging
import threading
import os
from typing import Optional

import docker

from deployments.common.retry import retry_with_backoff

logger = logging.getLogger(__name__)


# Defaults — can be overridden by Django settings or env vars on first init.
_DEFAULT_TIMEOUT = 60          # seconds for HTTP reads
_DEFAULT_PING_RETRIES = 3
_DEFAULT_PING_BACKOFF = 0.5


_pool_lock = threading.Lock()
_client_pool: dict[tuple[str, str, str], docker.DockerClient] = {}


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


def get_docker_client(base_url: Optional[str] = None, *, backend: str = "docker", cluster: str | None = None, endpoint: str | None = None) -> docker.DockerClient:
    """
    Return the shared ``DockerClient`` singleton.

    Clients are cached by ``(backend, cluster, endpoint)`` so a worker can safely
    talk to more than one runtime endpoint.
    """
    resolved_url = _resolve_base_url(endpoint or base_url)
    resolved_cluster = str(cluster or os.environ.get("SWARM_CLUSTER_NAME") or "default")
    key = (str(backend or "docker").strip().lower(), resolved_cluster, str(resolved_url or "from_env"))

    with _pool_lock:
        if key in _client_pool:
            return _client_pool[key]

        timeout = _resolve_timeout()
        client = (
            docker.DockerClient(base_url=resolved_url, timeout=timeout)
            if resolved_url
            else docker.from_env(timeout=timeout)
        )
        retry_with_backoff(
            client.ping,
            retries=_DEFAULT_PING_RETRIES,
            base_delay=_DEFAULT_PING_BACKOFF,
            max_delay=2.0,
            retry_on=(docker.errors.DockerException, OSError),
            label="docker.ping[%s:%s]" % (key[0], key[1]),
        )
        _client_pool[key] = client
        logger.info("Docker client initialised backend=%s cluster=%s endpoint=%s timeout=%s", key[0], key[1], key[2], timeout)
        return client

def reset_docker_client() -> None:
    """Close and clear all cached runtime-aware Docker clients."""
    with _pool_lock:
        clients = list(_client_pool.values())
        _client_pool.clear()
    for client in clients:
        try:
            client.close()
        except Exception:
            pass

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

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        backend: str = "docker",
        cluster: str | None = None,
        endpoint: str | None = None,
    ):
        self._client = get_docker_client(
            base_url,
            backend=backend,
            cluster=cluster,
            endpoint=endpoint,
        )

    @property
    def client(self) -> docker.DockerClient:
        """Return the shared Docker client (lazy + cached)."""
        return self._client

    def __call__(self) -> docker.DockerClient:
        """Backward-compat: old code did ``Client()()`` to fetch the client."""
        return self._client


__all__ = ["Client", "get_docker_client", "reset_docker_client"]
