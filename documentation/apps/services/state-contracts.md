# services state and choice contracts

## Service lifecycle state

Current Service status values are stopped, queued, deploying, running, failed, stopping, with succeeded retained for compatibility.

Operational meaning:
- stopped: desired/runtime state is not running.
- queued: desired state requests work but deployment has not begun/finished.
- deploying: an execution is actively changing runtime.
- running: current desired release is active and healthy enough for the Service state.
- failed: last lifecycle attempt failed and the Service is not in the running condition.
- stopping: a stop operation is in progress.
- succeeded: historical compatibility state; do not build new lifecycle logic around it.

desired_state is intent; status is lifecycle state. active_revision identifies the current executable release.

## ServiceRevision

Revisions are immutable. Deployments reference an exact revision. A rollback selects an existing revision and creates a new Deploy operation rather than editing history.

## ServiceShare

A share targets exactly one user OR one Messenger group. rules are normalized authorization policy; expires_at and is_active disable the grant. Group shares depend on live Messenger membership.

## Volume state

Volume service ownership is exclusive. Released/reclaim fields describe storage lifecycle, not application runtime readiness. Soft detach is not the same as physical deletion and does not necessarily free allocation quota until the model's release path completes.

## Secret state

ServiceSecret is stable identity; ServiceSecretVersion is immutable encrypted payload. Revisions reference a specific version so rotation cannot silently rewrite historical execution input.
