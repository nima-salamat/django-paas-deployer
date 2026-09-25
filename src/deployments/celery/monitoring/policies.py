"""
deployments/celery/monitoring/policies.py
-----------------------------------------
Central place for all monitoring thresholds and policy constants.

Changing a value here affects the entire monitoring subsystem; no magic
numbers should appear in the reconciliation rules themselves.
"""


# ---------------------------------------------------------------------------
# Deploy-pipeline timeouts
# ---------------------------------------------------------------------------

# How long a deploy may stay in pending/running before it is force-failed.
# Matches the existing MAX_DEPLOY_TIME_MINUTE setting (default 10 minutes).
DEPLOY_TIMEOUT_MINUTES: int = 10

# ---------------------------------------------------------------------------
# Service-level timeouts
# ---------------------------------------------------------------------------

# A service stuck in queued/deploying for longer than this is timed out.
# Uses the same threshold as deploy timeout so the two are in sync.
STUCK_QUEUED_MINUTES: int = 10

# Maximum time allowed for a stop operation before the monitor marks the
# service failed (container still present and running after this window).
STOP_TIMEOUT_MINUTES: int = 5

# ---------------------------------------------------------------------------
# Reconciliation grace windows
# ---------------------------------------------------------------------------

# When a container is found "not running" right after a successful deploy,
# wait this many seconds before declaring it dead.  This avoids flapping
# during an intentional restart (e.g. init scripts that exit and re-exec).
UNEXPECTED_DEATH_GRACE_SECONDS: int = 15

# ---------------------------------------------------------------------------
# Service statuses that the monitor actively reconciles
# ---------------------------------------------------------------------------

# Statuses that still need deploy-pipeline watch
ACTIVE_DEPLOY_STATUSES: tuple = (
    "pending",
    "running",
    "rolling_back",
)

# Service statuses that should be reconciled against Docker every tick
ACTIVE_SERVICE_STATUSES: tuple = (
    "queued",
    "deploying",
    "running",
    "stopping",
    # Include succeeded so the monitor can upgrade old rows to running when
    # the container is actually up, and downgrade to failed when it is not.
    "succeeded",
)


def runtime_policies() -> dict[str, int | bool]:
    """Read live operator thresholds from the unified Wagtail settings."""
    try:
        from core import settings_service as svc
        return {
            "deploy_timeout_minutes": svc.deploy_timeout_minutes(),
            "queued_timeout_minutes": svc.queued_timeout_minutes(),
            "stop_timeout_minutes": svc.stop_timeout_minutes(),
            "unexpected_death_grace_seconds": svc.unexpected_death_grace_seconds(),
            "monitor_enabled": svc.monitor_enabled(),
            "monitor_interval_seconds": svc.monitor_interval_seconds(),
            "monitor_batch_size": svc.monitor_batch_size(),
            "recovery_enabled": svc.monitor_recovery_enabled(),
            "max_recovery_attempts": svc.monitor_max_recovery_attempts(),
            "stale_base_build_minutes": svc.monitor_stale_base_build_minutes(),
            "stale_worker_seconds": svc.monitor_stale_worker_seconds(),
            "scheduler_lock_seconds": svc.monitor_scheduler_lock_seconds(),
        }
    except Exception:
        return {
            "deploy_timeout_minutes": 10, "queued_timeout_minutes": 10,
            "stop_timeout_minutes": 5, "unexpected_death_grace_seconds": 15,
            "monitor_enabled": True, "monitor_interval_seconds": 30,
            "monitor_batch_size": 100, "recovery_enabled": True,
            "max_recovery_attempts": 3, "stale_base_build_minutes": 30,
            "stale_worker_seconds": 90, "scheduler_lock_seconds": 20,
        }
