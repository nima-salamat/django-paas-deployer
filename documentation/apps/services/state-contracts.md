# services state and choice contracts

## Service lifecycle
status values are stopped, queued, deploying, running, failed and stopping, with succeeded retained for compatibility. desired_state is intent and may be stopped/running/deleted.

desired_state changes do not prove runtime success. status is the durable lifecycle projection produced by lifecycle/deployment workflows.

## Fencing and authority
lifecycle_generation is a monotonic desired-state fence. A stale worker must not overwrite newer intent.

active_revision is the exact immutable executable snapshot currently active. selected_deploy is a compatibility pointer into Deploy history and is not executable authority. task_id is correlation data, not a sole worker-ownership fence.

## ServiceRevision
Revisions are immutable. Deployment references an exact revision. Rollback selects an existing revision and creates a new deployment operation rather than editing history.

## ServiceShare
A share targets exactly one user or one Messenger group. rules are normalized authorization policy; expires_at/is_active disable the grant. Group shares depend on live Messenger membership.

## Volume
Service ownership is exclusive. Soft detach and physical release are different operations; release/reclaim fields describe storage lifecycle and quota, not runtime readiness.

## Secret
ServiceSecret is stable secret identity. ServiceSecretVersion is immutable encrypted payload. Revisions reference secret identity/version so rotation cannot silently rewrite historical execution input.