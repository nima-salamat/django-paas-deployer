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
  * They use deterministic 64-bit keys with a negligible collision probability.

We use a fixed namespace prefix so our locks never collide with locks
taken by other subsystems in the same database.
"""

from __future__ import annotations

import logging
import hashlib
import uuid
from contextlib import contextmanager
from typing import Iterator

from django.db import connection, transaction

logger = logging.getLogger(__name__)


# Domain separation keeps these locks distinct from other single-bigint
# advisory-lock users while preserving the full 64-bit deterministic key.
_LOCK_DOMAIN = b"deployer-lock-v1\0"


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

    def __init__(self, service_id: int | str, *, shared: bool = False, timeout_seconds: float = 0.0):
        self.service_id = service_id
        self.shared = shared
        self.timeout_seconds = timeout_seconds
        self._acquired = False
        self._connection_ref = None
        self._backend_pid: int | None = None

    def acquire(self) -> bool:
        """
        Try to acquire the advisory lock.  Returns True on success.

        Uses ``pg_try_advisory_lock`` (non-blocking) by default.  If
        ``timeout_seconds > 0`` we poll up to that duration.
        """
        key = self._key()
        if self.timeout_seconds <= 0:
            return self._try_acquire(key)

        # Polling fallback — only used when callers explicitly want to wait.
        import time
        deadline = time.time() + self.timeout_seconds
        while True:
            if self._try_acquire(key):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def release(self) -> None:
        if not self._acquired:
            return
        if not self.assert_held():
            self._acquired = False
            logger.warning(
                "DeploymentLock session was lost before release for service %s; "
                "the database session has already released its advisory lock.",
                self.service_id,
            )
            return
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", [self._key()])
                released = bool(cur.fetchone()[0])
        finally:
            self._acquired = False
            self._connection_ref = None
            self._backend_pid = None
        if not released:
            logger.warning("DeploymentLock was not held during release for service %s", self.service_id)
        else:
            logger.info("DeploymentLock released for service %s", self.service_id)

    def _try_acquire(self, key: int) -> bool:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s), pg_backend_pid();", [key])
            acquired, backend_pid = cur.fetchone()
        if not acquired:
            return False
        self._acquired = True
        self._connection_ref = connection.connection
        self._backend_pid = int(backend_pid)
        logger.info(
            "DeploymentLock acquired for service %s (key=%s backend_pid=%s)",
            self.service_id,
            key,
            backend_pid,
        )
        return True

    def assert_held(self) -> bool:
        """Prove this Python worker still owns the lock on its original DB session."""
        if not self._acquired or self._connection_ref is None:
            return False
        current = connection.connection
        if current is not self._connection_ref or bool(getattr(current, "closed", False)):
            return False
        key = self._key()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT pg_backend_pid(), EXISTS ("
                    "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                    "AND objsubid = 1 AND granted "
                    "AND classid = ((%s::bigint >> 32) & 4294967295)::oid "
                    "AND objid = (%s::bigint & 4294967295)::oid"
                    ");",
                    [key, key],
                )
                backend_pid, held = cur.fetchone()
        except Exception:
            logger.warning(
                "Could not verify advisory-lock session for service %s.",
                self.service_id,
                exc_info=True,
            )
            return False
        return int(backend_pid) == self._backend_pid and bool(held)

    def _key(self) -> int:
        value = self.service_id
        if isinstance(value, uuid.UUID):
            canonical = f"uuid:{value.hex}"
        elif isinstance(value, int) or str(value).strip().lstrip("+-").isdigit():
            canonical = f"int:{int(value)}"
        else:
            try:
                canonical = f"uuid:{uuid.UUID(str(value).strip()).hex}"
            except (TypeError, ValueError, AttributeError):
                canonical = f"str:{str(value).strip()}"
        digest = hashlib.blake2b(
            _LOCK_DOMAIN + canonical.encode("utf-8"),
            digest_size=8,
            person=b"deployer-lock",
        ).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

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


@contextmanager
def acquire_service_deployment_transaction_lock(
    service_id: int | str,
) -> Iterator[None]:
    """Fence a Service deletion for its complete surrounding transaction.

    The transaction-scoped PostgreSQL lock conflicts with the session lock
    held by deployment, stop, restart, and reconciliation workers. PostgreSQL
    releases it automatically on either commit or rollback, so a failed
    pre-delete cleanup cannot strand a session lock.
    """
    if not connection.in_atomic_block:
        raise RuntimeError(
            "Service deletion must hold its deployment transaction lock inside atomic()."
        )

    key = DeploymentLock(service_id)._key()
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s);", [key])
            acquired = bool(cur.fetchone()[0])
    else:
        # Non-PostgreSQL backends are used by fast unit tests. On databases
        # that implement row locks, hold the Service row until deletion ends.
        from services.models import Service

        acquired = Service.objects.select_for_update().filter(pk=service_id).exists()

    if not acquired:
        from deployments.common.exceptions import DeploymentLockError

        raise DeploymentLockError(
            f"Service {service_id} still has an active lifecycle operation; deletion was refused.",
            details={"service_id": str(service_id), "operation": "service_delete"},
        )
    yield


def is_service_locked(service_id: int) -> bool:
    """
    Best-effort check whether a service is currently locked.

    NOTE: advisory locks are inherently racy to inspect from outside
    the lock holder.  This function is for monitoring / diagnostics
    only — never use it to make deployment decisions.
    """
    key = DeploymentLock(service_id)._key()
    high = (key >> 32) & 0xFFFFFFFF
    low = key & 0xFFFFFFFF
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks "
            "WHERE locktype = 'advisory' "
            "AND objsubid = 1 AND granted "
            "AND classid = %s::oid AND objid = %s::oid;",
            [high, low],
        )
        return int(cur.fetchone()[0]) > 0


__all__ = [
    "DeploymentLock",
    "acquire_service_deployment_lock",
    "acquire_service_deployment_transaction_lock",
    "is_service_locked",
]
