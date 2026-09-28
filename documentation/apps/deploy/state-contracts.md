# deploy state and choice contracts

## Deploy.status

pending -> running -> succeeded/failed/cancelled, with rolling_back -> rolled_back when rollback completes. StateManager/deployment workers own transitions.

## rollback_status

not_required, pending, succeeded, failed. This describes rollback work, not primary deployment status.

## BaseRuntimeImage

The base-image lifecycle is PENDING, BUILDING, READY, FAILED or DISABLED. A row's state alone does not determine whether a rebuild is needed; compatible image identity/definition fingerprint and policy do.

## Execution ownership

execution_task_id plus worker_heartbeat_at identify the current worker owner. Replacement/recovery workers must not terminalize or clean resources belonging to a newer owner.

See ../../deployments/06-workers-concurrency-and-state.md and 08-base-images.md for the complete execution contract.
