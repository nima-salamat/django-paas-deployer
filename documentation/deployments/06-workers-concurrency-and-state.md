# 06 — Workers, concurrency and state

## Purpose

This is the concurrency contract for deployments. Read it before changing Celery tasks, state transitions, leases, cancellation or retry behavior.

## Celery queue topology

The current task routing in src/config/settings.py is:

| Task | Queue |
| --- | --- |
| deployments.celery.tasks.deploy | deployments |
| deployments.celery.tasks.run_db_deploy | deployments |
| deployments.celery.tasks.stop | operations |
| deployments.celery.tasks.build_base_runtime_image | base-images |
| deployments.celery.tasks.reclaim_released_volumes | operations |

Other application/catalog tasks may share deployment or operations queues where configured.

## Compose worker roles

### Default Celery worker

The compose service celery consumes:

~~~text
celery, deployments, operations
~~~

It exists so an installation can operate without the dedicated deployment worker.

### Dedicated deployment worker

The deployment-worker service consumes:

~~~text
deployments, operations
~~~

It uses prefork and defaults to DEPLOYMENT_WORKER_CONCURRENCY=2.

### Dedicated base-image worker

The base-image-worker service consumes only:

~~~text
base-images
~~~

It uses prefork and defaults to BASE_IMAGE_WORKER_CONCURRENCY=1.

This queue separation is deliberate. A deployment worker must not consume the base-image queue while synchronously waiting for a base-image build.

### Beat

celery-beat uses the Django Celery Beat DatabaseScheduler. The deployment monitor is scheduled frequently, then applies its own Redis gate and operator-configured cadence.

## Acknowledgement and prefetch

Current Celery settings use:

- CELERY_WORKER_PREFETCH_MULTIPLIER=1;
- CELERY_TASK_ACKS_LATE=True.

This is important for long-running Docker/build tasks.

## Deployment ownership

A deployment has two ownership layers:

1. a PostgreSQL advisory lock keyed by Service id;
2. task-id ownership persisted on Deploy/Service.

The advisory lock is held across the full deployment task.

StateManager.transition_deploy_if_owned() performs task ownership checks, cancellation fencing, legal transition validation and the final write under one Deploy row lock.

A separate read-then-write ownership check is unsafe.

## Per-Service advisory lock

deployments.core.state.locks.acquire_service_deployment_lock():

- keys the lock to the Service PK;
- is non-blocking by default;
- is held across Docker/build operations;
- releases on context exit;
- prevents two deployments of one Service from racing.

A lock observation is not a durable state fact. Do not use “lock is currently free” as permission to mutate without reacquiring it.

## Authoritative state machine

The legal transitions live in deployments.common.state_machine.py.

### Service

The current lifecycle includes:

~~~text
queued
deploying
running
stopping
stopped
failed
succeeded (legacy compatibility)
~~~

The exact allowed source -> target pairs are defined by the state-machine table.

### Deploy

~~~text
pending
running
succeeded
failed
cancelled
rolling_back
rolled_back
~~~

Terminal Deploy states can return to pending only through explicit re-execution/recovery paths.

Do not introduce a transition by assigning Deploy.status or Service.status directly.

## StateManager contract

deployments.core.state.manager.StateManager is the authoritative lifecycle mutation entry point.

For a normal transition it:

1. opens a short DB transaction;
2. locks the row;
3. verifies the legal transition;
4. writes bookkeeping fields;
5. records the state transition.

The transaction is intentionally short. It does not hold a database row lock while Docker performs a long build.

## Task-start fence

StateManager.lock_and_get_deployment():

- locks Deploy and Service;
- verifies task ownership;
- requires Service.QUEUED;
- transitions Service -> DEPLOYING;
- transitions Deploy PENDING -> RUNNING;
- stores execution_task_id and heartbeat.

This is the authoritative handoff from queued intent to executing work.

## Heartbeats and stale workers

StateManager.heartbeat_deploy() updates worker_heartbeat_at only while task ownership still matches.

On terminal transition, execution_task_id is cleared.

The monitor uses a stale-heartbeat threshold to identify workers that may have disappeared. Recovery must prove ownership from external resource identity before mutating runtime resources.

## Fencing rules

A stale worker must not:

- activate its old revision after a newer deployment won;
- mark the Service RUNNING after a newer deployment became authoritative;
- remove a runtime resource now owned by a newer deployment;
- clean a same-name resource merely because it exists.

The system uses task-id ownership, previous_deploy_id checks, deployment labels and row locks together to prevent these cases.

## Cancellation races

The pure cancellation policy in deployments.application.cancellation.py defines:

~~~text
PENDING
  -> immediate CANCELLED

RUNNING / ROLLING_BACK
  -> cancel_requested token
  -> owning worker stops work and cleans safely
  -> CANCELLED
~~~

The final owned state transition re-checks cancellation under the Deploy lock. A cancellation committed first therefore prevents a later success transition.

A pending deployment cancelled before the worker starts can be finalized by the monitor if the Celery task never arrives.

## Retry behavior

The application deploy task has max_retries=3 with a 15-second default delay. It retries only exceptions classified as recoverable.

The database deploy task has max_retries=2 with a 20-second default delay and uses the retryability predicate for transient conditions.

The unified exceptions contract intentionally marks deterministic build/configuration/programming failures as non-recoverable by default.

Unknown Python exceptions are converted to internal platform failures rather than blindly retried.

## Database duplicate delivery

run_db_deploy uses the same Service advisory lock and state gate.

A duplicate delivery that reaches a Service already being deployed is intentionally prevented from starting a second database mutation.

## Base-image concurrency

Base images have their own row lifecycle and task ownership.

If another deployment already owns BUILDING:

- a compatible local image may be used immediately;
- otherwise the second deployment waits on the shared registry row;
- it does not create a duplicate build for the same base identity;
- the wait uses the deployment's dedicated base-image phase budget.

BaseRuntimeImageLease protects a shared artifact from cleanup while a deployment is using it.

## Redis is coordination, not authoritative state

Redis is used for:

- Celery transport/results;
- monitor scheduler gating;
- bounded orphan-recovery attempts.

Redis keys do not replace Deploy/Service state or the state machine.

## What this layer must NOT do

Do not:

- hold DB row locks across long Docker operations;
- use Redis lock presence as authoritative deployment ownership;
- retry every DeploymentError;
- bypass StateManager for normal lifecycle writes;
- let a stale worker perform cleanup after ownership is lost;
- make tenant configuration select queues or worker concurrency;
- add a second independent lifecycle state machine.

## Related code

- src/config/settings.py
- compose.yaml
- src/deployments/celery/tasks.py
- src/deployments/celery/schedules.py
- src/deployments/celery/services/deploy_service.py
- src/deployments/core/state/locks.py
- src/deployments/core/state/manager.py
- src/deployments/common/state_machine.py
- src/deployments/common/retry.py
- src/deployments/application/cancellation.py
