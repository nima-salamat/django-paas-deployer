"""Distributed build concurrency control backed by Redis.

The deployment worker pool may be scaled horizontally; this semaphore keeps
Docker builds globally bounded across all workers.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from contextlib import AbstractContextManager
from typing import Any

from .exceptions import DeploymentError

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
end
return 0
"""




def _parallelism() -> int:
    try:
        from core import settings_service
        return max(1, int(settings_service.build_parallelism()))
    except Exception:
        try:
            return max(1, int(os.getenv('DEPLOY_BUILD_PARALLELISM', '1')))
        except (TypeError, ValueError):
            return 1


def _lease_seconds() -> int:
    try:
        from core import settings_service
        return max(60, int(settings_service.build_slot_lease_seconds()))
    except Exception:
        try:
            return max(60, int(os.getenv('DEPLOY_BUILD_SLOT_LEASE_SECONDS', '900')))
        except (TypeError, ValueError):
            return 900

def _wait_seconds() -> int:
    try:
        from core import settings_service
        return max(1, int(settings_service.build_max_wait_minute()) * 60)
    except Exception:
        try:
            return max(60, int(os.getenv('DEPLOY_BUILD_MAX_WAIT_MINUTE', '5')) * 60)
        except (TypeError, ValueError):
            return 300

def _redis_client():
    import redis
    url = os.getenv('CELERY_BROKER_URL') or os.getenv('REDIS_URL') or 'redis://redis:6379/0'
    return redis.Redis.from_url(url, decode_responses=True)


class BuildSlot(AbstractContextManager):
    def __init__(self, *, deployment_id: Any, logger=None):
        self.deployment_id = str(deployment_id)
        self.logger = logger
        self.redis = None
        self.key = None
        self.token = uuid.uuid4().hex
        self.lease_seconds = 0
        self._heartbeat_stop = None
        self._heartbeat_thread = None
        self._lease_lost = False

    def __enter__(self):
        count = _parallelism()
        if count <= 0:
            count = 1
        started = time.monotonic()
        lease_seconds = _lease_seconds()
        while True:
            self.redis = _redis_client()
            for index in range(count):
                key = f"deployer:build-slot:{index}"
                try:
                    if self.redis.set(key, self.token, nx=True, ex=lease_seconds):
                        self.key = key
                        self.lease_seconds = lease_seconds
                        self._heartbeat_stop = threading.Event()
                        self._heartbeat_thread = threading.Thread(
                            target=self._heartbeat_loop,
                            name=f"build-slot-heartbeat-{self.deployment_id}",
                            daemon=True,
                        )
                        self._heartbeat_thread.start()
                        if self.logger:
                            try:
                                self.logger.info(
                                    "build_slot_acquired",
                                    "Acquired build slot.",
                                    details={"slot": index, "parallelism": count},
                                )
                            except TypeError:
                                # Standard logging.Logger does not accept the
                                # DeploymentLogger ``details=`` keyword.
                                self.logger.info(
                                    "build_slot_acquired slot=%s parallelism=%s",
                                    index,
                                    count,
                                )
                        return self
                except Exception as exc:
                    raise DeploymentError(
                        f"Build concurrency control unavailable: {exc}",
                        stage="build_slot",
                        recoverable=True,
                    ) from exc
            if time.monotonic() - started >= _wait_seconds():
                raise DeploymentError(
                    "No Docker build slot became available before the configured wait timeout.",
                    stage="build_slot",
                    recoverable=True,
                )
            time.sleep(0.5)

    def _renew_lease(self) -> bool:
        if self.redis is None or self.key is None:
            return False
        try:
            renewed = self.redis.eval(
                _RENEW_SCRIPT,
                1,
                self.key,
                self.token,
                str(self.lease_seconds),
            )
            if int(renewed or 0) == 1:
                return True
            self._lease_lost = True
            if self.logger:
                self.logger.error(
                    "build_slot_lease_lost: Redis lease token no longer owns slot"
                )
            return False
        except Exception:
            # A transient heartbeat failure must not silently give another
            # builder ownership. Mark the lease uncertain and let the current
            # build finish; the short TTL will recover the slot.
            self._lease_lost = True
            if self.logger:
                self.logger.warning(
                    "build_slot_renew_failed: Redis heartbeat failed; ownership is uncertain"
                )
            return False

    def _heartbeat_loop(self) -> None:
        stop = self._heartbeat_stop
        if stop is None:
            return
        interval = max(1.0, min(30.0, self.lease_seconds / 3.0))
        while not stop.wait(interval):
            if not self._renew_lease():
                # Do not spin on a broken Redis lease.
                return

    def __exit__(self, exc_type, exc, tb):
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=max(1.0, min(5.0, self.lease_seconds / 2.0)))
        if self.redis is not None and self.key is not None:
            try:
                self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
            except Exception:
                if self.logger:
                    try:
                        self.logger.warning(
                            "build_slot_release_failed",
                            "Could not release build slot; lease will expire automatically.",
                        )
                    except TypeError:
                        self.logger.warning(
                            "build_slot_release_failed: lease will expire automatically"
                        )
        return False
