# deploy state and choice contracts

## Deploy.status
The deployment state machine is pending -> running -> succeeded/failed/cancelled, with rollback work represented separately. StateManager/deployment workers own transitions.

## rollback_status
not_required, pending, succeeded and failed describe rollback work, not primary deployment status.

## Execution ownership
execution_task_id identifies the worker attempt currently allowed to mutate execution state. worker_heartbeat_at is liveness evidence used by stale-worker recovery. Recovery must fence a stale owner before terminalization or cleanup.

## Phase timestamps
base_image_wait_started_at marks the start of waiting for a compatible base runtime image/build. base_image_ready_at marks availability of that image. application_started_at marks application runtime start before readiness evaluation. operation_started_at marks the explicit operation start. completed_at marks terminal completion. These timestamps are not interchangeable progress fields.

## BaseRuntimeImage
Lifecycle is PENDING, BUILDING, READY, FAILED or DISABLED. Compatibility is determined using runtime identity/definition fingerprint and policy; a READY compatible image is not rebuilt merely because a deployment was retried.

definition_fingerprint identifies the normalized build definition. rebuild_requested/rebuild_requested_at represent explicit rebuild policy. build_task_id/build_owner_deployment_id fence an in-progress build. last_error_details stores structured diagnostics.

See deployments/06-workers-concurrency-and-state.md and deployments/08-base-images.md for execution/recovery detail.