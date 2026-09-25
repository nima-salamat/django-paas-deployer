"""Desired-state fencing via Service.lifecycle_generation."""
from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


class StaleLifecycleError(Exception):
    """Raised when a worker holds a stale lifecycle generation."""

    def __init__(self, message: str, *, service_id=None, expected: int | None = None, actual: int | None = None):
        super().__init__(message)
        self.service_id = service_id
        self.expected = expected
        self.actual = actual


def capture_generation(service) -> int:
    """Return the current lifecycle generation for *service* (no lock)."""
    return int(getattr(service, "lifecycle_generation", 0) or 0)


@transaction.atomic
def bump_lifecycle(service_id, *, desired_state: str | None = None) -> int:
    """
    Increment lifecycle_generation and optionally set desired_state.

    Returns the new generation. Callers that start deploy/stop/delete must
    capture this value and pass it through to completion/CAS helpers.
    """
    from services.models import Service

    service = Service.objects.select_for_update().filter(pk=service_id).first()
    if service is None:
        raise StaleLifecycleError(f"Service {service_id} does not exist.", service_id=service_id)

    Service.objects.filter(pk=service_id).update(
        lifecycle_generation=F("lifecycle_generation") + 1,
    )
    service.refresh_from_db(fields=["lifecycle_generation", "desired_state"])
    new_gen = int(service.lifecycle_generation or 0)

    if desired_state is not None:
        Service.objects.filter(pk=service_id).update(desired_state=desired_state)
        service.desired_state = desired_state

    logger.info(
        "lifecycle_bump service=%s generation=%s desired_state=%s",
        service_id, new_gen, desired_state or service.desired_state,
    )
    return new_gen


@transaction.atomic
def cas_desired_state(
    service_id,
    *,
    expected_generation: int,
    desired_state: str,
) -> bool:
    """
    Compare-and-set desired_state only if lifecycle_generation still matches.

    Returns True if the update applied, False if the worker is stale.
    Does **not** bump the generation (the intent that owns this generation
    already bumped it when the operation started).
    """
    from services.models import Service

    updated = Service.objects.filter(
        pk=service_id,
        lifecycle_generation=int(expected_generation),
    ).update(desired_state=desired_state)
    if not updated:
        current = (
            Service.objects.filter(pk=service_id)
            .values_list("lifecycle_generation", flat=True)
            .first()
        )
        logger.warning(
            "cas_desired_state rejected service=%s expected_gen=%s actual_gen=%s wanted=%s",
            service_id, expected_generation, current, desired_state,
        )
        return False
    return True


@transaction.atomic
def assert_generation(service_id, expected_generation: int) -> None:
    """Raise StaleLifecycleError if generation no longer matches."""
    from services.models import Service

    current = (
        Service.objects.select_for_update()
        .filter(pk=service_id)
        .values_list("lifecycle_generation", flat=True)
        .first()
    )
    if current is None:
        raise StaleLifecycleError(
            f"Service {service_id} does not exist.",
            service_id=service_id,
            expected=expected_generation,
        )
    if int(current) != int(expected_generation):
        raise StaleLifecycleError(
            f"Stale lifecycle generation for service {service_id}: "
            f"expected {expected_generation}, actual {current}.",
            service_id=service_id,
            expected=int(expected_generation),
            actual=int(current),
        )


@transaction.atomic
def mark_deleted(service_id) -> int:
    """Bump generation and set desired_state=deleted. Returns new generation."""
    return bump_lifecycle(service_id, desired_state="deleted")


def is_deleted_generation(service) -> bool:
    """True when the service desired_state is terminal deleted."""
    return str(getattr(service, "desired_state", "") or "").lower() == "deleted"
