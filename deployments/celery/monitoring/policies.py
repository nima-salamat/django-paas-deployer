"""
deployments/celery/monitoring/policies.py
-----------------------------------------
Central place for all monitoring thresholds and policy constants.

Changing a value here affects the entire monitoring subsystem; no magic
numbers should appear in the reconciliation rules themselves.
"""

from core.global_settings.config import MAX_DEPLOY_TIME_MINUTE

# ---------------------------------------------------------------------------
# Deploy-pipeline timeouts
# ---------------------------------------------------------------------------

# How long a deploy may stay in pending/running before it is force-failed.
# Matches the existing MAX_DEPLOY_TIME_MINUTE setting (default 10 minutes).
DEPLOY_TIMEOUT_MINUTES: int = MAX_DEPLOY_TIME_MINUTE

# ---------------------------------------------------------------------------
# Service-level timeouts
# ---------------------------------------------------------------------------

# A service stuck in queued/deploying for longer than this is timed out.
# Uses the same threshold as deploy timeout so the two are in sync.
STUCK_QUEUED_MINUTES: int = MAX_DEPLOY_TIME_MINUTE

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
