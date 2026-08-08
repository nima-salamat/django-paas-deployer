"""
deployments/common/state_machine.py
-----------------------------------
Explicit state machine for Service and Deploy lifecycle.

The previous codebase mutated ``Service.status`` and ``Deploy.status`` from
many places (deploy_service, stop_service, monitoring actions, schedules,
sink, tasks) with INCONSISTENT validation:
  * ``lock_and_get_deployment`` checked ``QUEUED``.
  * ``lock_and_start_stopping`` did NOT check anything.
  * ``sync_legacy_*`` did bare ``.update()`` with no check at all — a
    retried deploy task could overwrite a clean stop with FAILED, or
    overwrite a FAILED with RUNNING.
  * ``sink._update_deploy_row`` could overwrite a monitor-set FAILED
    with SUCCEEDED.

This module is the single source of truth for which transitions are
legal.  Every state-mutating call site MUST go through
``StateMachine.transition()`` (or one of the typed helpers in
``deployments/core/state/``).

Design
------
* States are string enums (we keep them as plain ``str`` so they
  interoperate with Django's CharField choices without conversion).
* The transition table is a module-level constant — easy to audit, easy
  to test.
* ``InvalidTransition`` is raised for any disallowed transition.  The
  caller decides whether to swallow it (idempotent) or propagate it.
* Two state machines are defined: ``SERVICE`` and ``DEPLOY``.  They are
  independent — a Service can transition QUEUED -> DEPLOYING -> RUNNING
  while a Deploy transitions PENDING -> RUNNING -> SUCCEEDED, but the
  orchestrator is responsible for keeping them aligned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


# ---------------------------------------------------------------------------
# Service states
# ---------------------------------------------------------------------------

SERVICE_QUEUED = "queued"
SERVICE_DEPLOYING = "deploying"
SERVICE_RUNNING = "running"
SERVICE_STOPPING = "stopping"
SERVICE_STOPPED = "stopped"
SERVICE_FAILED = "failed"
SERVICE_SUCCEEDED = "succeeded"  # legacy alias for RUNNING

SERVICE_STATES: tuple[str, ...] = (
    SERVICE_QUEUED,
    SERVICE_DEPLOYING,
    SERVICE_RUNNING,
    SERVICE_STOPPING,
    SERVICE_STOPPED,
    SERVICE_FAILED,
    SERVICE_SUCCEEDED,
)

# ---------------------------------------------------------------------------
# Deploy states
# ---------------------------------------------------------------------------

DEPLOY_PENDING = "pending"
DEPLOY_RUNNING = "running"
DEPLOY_SUCCEEDED = "succeeded"
DEPLOY_FAILED = "failed"
DEPLOY_CANCELLED = "cancelled"
DEPLOY_ROLLING_BACK = "rolling_back"
DEPLOY_ROLLED_BACK = "rolled_back"

DEPLOY_STATES: tuple[str, ...] = (
    DEPLOY_PENDING,
    DEPLOY_RUNNING,
    DEPLOY_SUCCEEDED,
    DEPLOY_FAILED,
    DEPLOY_CANCELLED,
    DEPLOY_ROLLING_BACK,
    DEPLOY_ROLLED_BACK,
)

# ---------------------------------------------------------------------------
# Transition tables
# ---------------------------------------------------------------------------

# A transition (src, dst) is allowed iff (src, dst) in the table OR
# src == dst (idempotent self-transition).  ``None`` source matches any
# state (used for "create" transitions on a freshly initialised row).

SERVICE_TRANSITIONS: FrozenSet[tuple[str | None, str]] = frozenset({
    # Normal lifecycle
    (None, SERVICE_QUEUED),                # brand new service
    (SERVICE_QUEUED, SERVICE_DEPLOYING),   # deploy task picks it up
    (SERVICE_DEPLOYING, SERVICE_RUNNING),  # deploy succeeded
    (SERVICE_DEPLOYING, SERVICE_FAILED),   # deploy failed
    (SERVICE_DEPLOYING, SERVICE_STOPPED),  # deploy failed but container cleaned

    # Stop lifecycle
    (SERVICE_RUNNING, SERVICE_STOPPING),
    (SERVICE_FAILED, SERVICE_STOPPING),    # operator stops a failed service
    (SERVICE_STOPPING, SERVICE_STOPPED),
    (SERVICE_STOPPING, SERVICE_FAILED),    # stop itself failed

    # Recovery
    (SERVICE_STOPPED, SERVICE_QUEUED),     # redeploy
    (SERVICE_FAILED, SERVICE_QUEUED),      # retry after fixing
    (SERVICE_STOPPED, SERVICE_DEPLOYING),  # redeploy directly
    (SERVICE_FAILED, SERVICE_DEPLOYING),   # operator forced redeploy
    (SERVICE_RUNNING, SERVICE_DEPLOYING),  # new deploy over a running one

    # Legacy alias: SUCCEEDED == RUNNING
    (SERVICE_SUCCEEDED, SERVICE_RUNNING),
    (SERVICE_SUCCEEDED, SERVICE_STOPPING),
    (SERVICE_SUCCEEDED, SERVICE_DEPLOYING),
    (SERVICE_RUNNING, SERVICE_SUCCEEDED),
})


DEPLOY_TRANSITIONS: FrozenSet[tuple[str | None, str]] = frozenset({
    (None, DEPLOY_PENDING),                # new deploy row
    (DEPLOY_PENDING, DEPLOY_RUNNING),      # task picks it up
    (DEPLOY_PENDING, DEPLOY_CANCELLED),    # cancelled before start
    (DEPLOY_PENDING, DEPLOY_FAILED),       # validation failure before start

    (DEPLOY_RUNNING, DEPLOY_SUCCEEDED),
    (DEPLOY_RUNNING, DEPLOY_FAILED),
    (DEPLOY_RUNNING, DEPLOY_CANCELLED),
    (DEPLOY_RUNNING, DEPLOY_ROLLING_BACK),

    (DEPLOY_ROLLING_BACK, DEPLOY_ROLLED_BACK),
    (DEPLOY_ROLLING_BACK, DEPLOY_FAILED),  # rollback itself failed

    # Recovery from terminal states (operator re-triggers)
    (DEPLOY_FAILED, DEPLOY_PENDING),
    (DEPLOY_CANCELLED, DEPLOY_PENDING),
    (DEPLOY_ROLLED_BACK, DEPLOY_PENDING),
})


@dataclass(frozen=True)
class InvalidTransition(Exception):
    """Raised when a state transition is not in the allowed table."""
    entity: str
    src: str | None
    dst: str
    allowed: tuple[str, ...]

    def __str__(self) -> str:  # noqa: D401 - keep exception message informative
        return (
            f"Invalid {self.entity} state transition: "
            f"{self.src!r} -> {self.dst!r}. "
            f"Allowed targets from {self.src!r}: {self.allowed}"
        )


# Make it a real Exception subclass (dataclass + Exception is awkward)
class InvalidTransition(Exception):
    def __init__(self, entity: str, src: str | None, dst: str,
                 allowed: tuple[str, ...]) -> None:
        self.entity = entity
        self.src = src
        self.dst = dst
        self.allowed = allowed
        super().__init__(str(self))

    def __str__(self) -> str:  # noqa: D401
        return (
            f"Invalid {self.entity} state transition: "
            f"{self.src!r} -> {self.dst!r}. "
            f"Allowed targets from {self.src!r}: {self.allowed}"
        )


def _check(table: FrozenSet[tuple[str | None, str]], entity: str,
           src: str | None, dst: str) -> None:
    if src == dst:
        return  # idempotent
    if (src, dst) in table or (None, dst) in table:
        return
    allowed = tuple(sorted({d for (s, d) in table if s == src}))
    raise InvalidTransition(entity, src, dst, allowed)


def check_service_transition(src: str | None, dst: str) -> None:
    """Raise InvalidTransition if Service ``src`` -> ``dst`` is illegal."""
    _check(SERVICE_TRANSITIONS, "Service", src, dst)


def check_deploy_transition(src: str | None, dst: str) -> None:
    """Raise InvalidTransition if Deploy ``src`` -> ``dst`` is illegal."""
    _check(DEPLOY_TRANSITIONS, "Deploy", src, dst)


def is_service_terminal(state: str) -> bool:
    """A terminal Service state cannot transition except via explicit recovery."""
    return state in (SERVICE_STOPPED, SERVICE_FAILED, SERVICE_SUCCEEDED)


def is_deploy_terminal(state: str) -> bool:
    return state in (
        DEPLOY_SUCCEEDED, DEPLOY_FAILED, DEPLOY_CANCELLED, DEPLOY_ROLLED_BACK,
    )


__all__ = [
    # state constants
    "SERVICE_QUEUED", "SERVICE_DEPLOYING", "SERVICE_RUNNING",
    "SERVICE_STOPPING", "SERVICE_STOPPED", "SERVICE_FAILED",
    "SERVICE_SUCCEEDED", "SERVICE_STATES",
    "DEPLOY_PENDING", "DEPLOY_RUNNING", "DEPLOY_SUCCEEDED",
    "DEPLOY_FAILED", "DEPLOY_CANCELLED", "DEPLOY_ROLLING_BACK",
    "DEPLOY_ROLLED_BACK", "DEPLOY_STATES",
    # transition tables
    "SERVICE_TRANSITIONS", "DEPLOY_TRANSITIONS",
    # functions
    "InvalidTransition",
    "check_service_transition",
    "check_deploy_transition",
    "is_service_terminal",
    "is_deploy_terminal",
]
