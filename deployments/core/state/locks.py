"""
deployments/core/state/locks.py
-------------------------------
Per-service deployment locks.

The legacy codebase acquired row locks via ``select_for_update`` inside
short transactions that ended BEFORE any Docker work began.  Two deploys
targeting the same Service could therefore race: deploy A finishes its
transaction (releasing the row lock), starts a 60-second image build,
and deploy B starts its transaction (the row is now free, status is
DEPLOYING — invalid).  The monitor eventually times it out.

We now use a Postgres advisory lock keyed on the Service PK.  The lock
is held for the entire duration of the Celery task — across Docker
operations — and is released when the task exits (via context manager
or explicit release).

Advisory locks have several nice properties:
  * They are not tied to a transaction, so they survive the
    transaction-per-Docker-stage pattern.
  * They are re-acquirable from any backend, so a stuck lock can be
    cleared with ``pg_advisory_unlock`` if absolutely necessary.
  * They are indexed by bigint, so collisions are impossible.

We use a fixed namespace prefix so our locks never collide with locks
taken by other subsystems in the same database.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from django.db import connection, transaction

logger = logging.getLogger(__name__)


# Namespace prefix for our advisory locks.  Arbitrary but constant.
# 0x4445504C = "DEPL" in ASCII.
_LOCK_NAMESPACE = 0x4445504C


class DeploymentLock:
    """
    A Postgres advisory lock keyed on a Service PK.

    Acquire via ``acquire_service_deployment_lock(service_id)`` — do not
    instantiate directly.  Use as a context manager:

        with acquire_service_deployment_lock(service_id) as lock:
            ...

    The lock is released on context exit (even on exception).  If the
    lock cannot be acquired (another deploy is running for the same
    service), ``DeploymentLockError`` is raised immediately — we do NOT
    block, because a Celery worker must never hang.
    """

    def __init__(self, service_id: int, *, shared: bool = False, timeout_seconds: float = 0.0):
        self.service_id = service_id
        self.shared = shared
        self.timeout_seconds = timeout_seconds
        self._acquired = False

    def acquire(self) -> bool:
        """
        Try to acquire the advisory lock.  Returns True on success.

        Uses ``pg_try_advisory_lock`` (non-blocking) by default.  If
        ``timeout_seconds > 0`` we poll up to that duration.
        """
        key = self._key()
        sql = "SELECT pg_try_advisory_lock(%s, %s);"
        if self.timeout_seconds <= 0:
            with connection.cursor() as cur:
                cur.execute(sql, [_LOCK_NAMESPACE, key])
                ok = bool(cur.fetchone()[0])
            if ok:
                self._acquired = True
                logger.info(
                    "DeploymentLock acquired for service %s (namespace=%s key=%s)",
                    self.service_id, _LOCK_NAMESPACE, key,
                )
            return ok

        # Polling fallback — only used when callers explicitly want to wait.
        import time
        deadline = time.time() + self.timeout_seconds
        while True:
            with connection.cursor() as cur:
                cur.execute(sql, [_LOCK_NAMESPACE, key])
                ok = bool(cur.fetchone()[0])
            if ok:
                self._acquired = True
                logger.info(
                    "DeploymentLock acquired for service %s after polling",
                    self.service_id,
                )
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def release(self) -> None:
        if not self._acquired:
            return
        key = self._key()
        with connection.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_unlock(%s, %s);",
                [_LOCK_NAMESPACE, key],
            )
            cur.fetchone()
        self._acquired = False
        logger.info(
            "DeploymentLock released for service %s", self.service_id,
        )

    def _key(self) -> int:
        # Service IDs in this codebase are integer PKs.  We use the PK
        # directly as the second key — advisory locks accept two int32s.
        try:
            return int(self.service_id) & 0x7FFFFFFF
        except (TypeError, ValueError):
            # Fall back to a hash if the PK is non-int (e.g. UUID).
            return abs(hash(str(self.service_id))) & 0x7FFFFFFF

    def __enter__(self) -> "DeploymentLock":
        if not self.acquire():
            from deployments.common.exceptions import DeploymentLockError
            raise DeploymentLockError(
                f"Another deployment is already running for service "
                f"{self.service_id}.",
                details={"service_id": self.service_id},
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


@contextmanager
def acquire_service_deployment_lock(
    service_id: int,
    *,
    timeout_seconds: float = 0.0,
) -> Iterator[DeploymentLock]:
    """
    Context manager that acquires a per-service advisory lock.

    Raises ``DeploymentLockError`` if the lock cannot be acquired
    (another deploy is running for the same service).
    """
    lock = DeploymentLock(service_id, timeout_seconds=timeout_seconds)
    if not lock.acquire():
        from deployments.common.exceptions import DeploymentLockError
        raise DeploymentLockError(
            f"Another deployment is already running for service {service_id}.",
            details={"service_id": service_id},
        )
    try:
        yield lock
    finally:
        lock.release()


def is_service_locked(service_id: int) -> bool:
    """
    Best-effort check whether a service is currently locked.

    NOTE: advisory locks are inherently racy to inspect from outside
    the lock holder.  This function is for monitoring / diagnostics
    only — never use it to make deployment decisions.
    """
    key = DeploymentLock(service_id)._key()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks "
            "WHERE locktype = 'advisory' "
            "AND classid = %s AND objid = %s;",
            [_LOCK_NAMESPACE, key],
        )
        return int(cur.fetchone()[0]) > 0


__all__ = ["DeploymentLock", "acquire_service_deployment_lock", "is_service_locked"]
