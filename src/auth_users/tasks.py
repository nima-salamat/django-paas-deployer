"""Maintenance tasks owned by the authentication subsystem."""
from __future__ import annotations

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger("auth_users.tasks")


@shared_task(
    bind=True,
    max_retries=0,
    name="auth_users.tasks.cleanup_expired_jwt_blacklist",
)
def cleanup_expired_jwt_blacklist(self) -> dict[str, str]:
    """Remove expired SimpleJWT outstanding/blacklisted token records."""
    call_command("flushexpiredtokens")
    logger.info("Expired JWT blacklist records cleaned up.")
    return {"status": "ok"}
