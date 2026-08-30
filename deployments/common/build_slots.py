"""Distributed build concurrency control backed by Redis.

The deployment worker pool may be scaled horizontally; this semaphore keeps
Docker builds globally bounded across all workers.
"""
from __future__ import annotations

import os
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


def _parallelism() -> int:
    try:
        from core import settings_service
        return max(1, int(settings_service.build_parallelism()))
    except Exception:
        try:
            return max(1, int(os.getenv('DEPLOY_BUILD_PARALLELISM', '1')))
        except (TypeError, ValueError):
            return 1


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

    def __enter__(self):
        count = _parallelism()
        if count <= 0:
            count = 1
        started = time.monotonic()
        while True:
            self.redis = _redis_client()
            for index in range(count):
                key = f"deployer:build-slot:{index}"
                try:
                    if self.redis.set(key, self.token, nx=True, ex=600):
                        self.key = key
                        if self.logger:
                            self.logger.info("build_slot_acquired", "Acquired build slot.", details={"slot": index, "parallelism": count})
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

    def __exit__(self, exc_type, exc, tb):
        if self.redis is not None and self.key is not None:
            try:
                self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
            except Exception:
                if self.logger:
                    self.logger.warning("build_slot_release_failed", "Could not release build slot; lease will expire automatically.")
        return False
