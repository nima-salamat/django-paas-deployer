# 06 — Workers, concurrency and state

## Purpose

This is the concurrency contract. Read it before changing Celery tasks, locks, lifecycle state, cancellation, retry, leases or monitor recovery.

The key principle is:

> A database row records lifecycle state; a lock/fence grants permission to mutate it; a worker owns the external side effect only while that ownership remains valid.

## Worker topology

Current Celery routing in `src/config/settings.py`:

| Task | Queue | Role |
|---|---|---|
| `deployments.celery.tasks.deploy` | `deployments` | application deployment |
| `deployments.celery.tasks.run_db_deploy` | `deployments` | database deployment |
| `deployments.celery.tasks.stop` | `operations` | service stop |
| `deployments.celery.tasks.build_base_runtime_image` | `base-images` | shared operator base-image build |
| `deployments.celery.tasks.reclaim_released_volumes` | `operations` | retained-volume reclamation |

Scheduled monitor/sync work is defined in Celery Beat.

### Compose consumers

- `celery`: `celery,deployments,operations`
- `deployment-worker`: `deployments,operations`, prefork, default concurrency 2
- `base-image-worker`: `base-images`, prefork, default concurrency 1
- `celery-beat`: emits scheduled tasks

Base-image isolation is intentional: deployment workers synchronously waiting on a base-image task must not also consume the queue that task requires.

## Celery delivery semantics

Current settings include:

- prefetch multiplier 1;
- late acknowledgements;
- broker publish retry;
- broker startup retry.

These improve behavior around long-running infrastructure tasks, but they do **not** make deployment idempotent by themselves.

State/ownership mechanisms are still required.

## How application deployment is acquired

### Entry

`deployments.celery.tasks.deploy()`

### Preconditions

- Deploy exists;
- it is not already cancelled;
- database-platform guard has not redirected it to `run_db_deploy`.

### Handoff

```text
Celery task id
    -> DeployService.execute(task_id=...)
    -> acquire_service_deployment_lock(service_id)
    -> StateManager.lock_and_get_deployment(deploy_id, task_id=...)
```

The task id becomes the execution fence.

## Service advisory lock

**Path:** `core/state/locks.py`

### Called by

`DeployService.execute()`, `StopService.execute()`, and database deployment.

### Preconditions

Service id exists.

### Contract

`acquire_service_deployment_lock()` acquires a PostgreSQL advisory lock keyed by Service id.

By default it is non-blocking and raises `DeploymentLockError` immediately if another operation owns the Service.

### Why a database row lock is insufficient

A row lock from `select_for_update()` lasts only for a transaction. Docker build/runtime work can last minutes.

Without a transaction-independent lock:

```text
A locks row
A commits
A builds image
B locks same row
B starts conflicting Docker work
```

The advisory lock spans the external work.

### Must not

Do not use `is_service_locked()` as authorization to mutate. It is diagnostic and inherently racy. Acquire the lock yourself.

## StateManager

**Path:** `core/state/manager.py`

### Contract

StateManager is the authoritative persistence port for lifecycle transitions.

`transition_deploy_if_owned()` is the critical fencing primitive.

Under one Deploy row lock it:

1. checks task ownership;
2. checks terminal status where requested;
3. applies the cancellation fence;
4. checks legal state transition;
5. writes status/bookkeeping;
6. clears execution ownership on terminal state.

### Why

Ownership, cancellation and transition legality are one atomic decision. Splitting them into separate reads/writes creates race windows.

## State machine

**Path:** `common/state_machine.py`

The actual legal transition table is code. This document explains its meaning.

### Deploy

| State | Meaning | Normal entrants | Normal exits | Forbidden assumption |
|---|---|---|---|---|
| PENDING | queued/not yet executing | creation/re-execution | RUNNING, CANCELLED, FAILED | runtime already changed |
| RUNNING | worker owns execution | task start | SUCCEEDED, FAILED, CANCELLED, ROLLING_BACK | container must already exist |
| ROLLING_BACK | failure recovery is restoring previous runtime | failure path | ROLLED_BACK, FAILED | rollback already succeeded |
| SUCCEEDED | execution completed and activation was committed | lifecycle completion | PENDING only via explicit re-execution | can be changed by an old worker |
| FAILED | execution failed | error path | PENDING via explicit retry/re-execution | automatically recoverable |
| CANCELLED | cancellation won | cancellation path | PENDING via explicit re-execution | Celery retry may resurrect it |
| ROLLED_BACK | previous release restored | rollback path | PENDING via explicit re-execution | equivalent to a successful new deploy |

### Service

| State | Meaning |
|---|---|
| QUEUED | service expects deployment work |
| DEPLOYING | deployment work is executing |
| RUNNING | service is considered active |
| STOPPING | stop operation owns the shutdown |
| STOPPED | desired/runtime state is stopped |
| FAILED | runtime/deployment failure is authoritative |
| SUCCEEDED | legacy compatibility alias treated as a pre-existing success/running state |

Service and Deploy machines are independent. Lifecycle code aligns them; do not assume changing one row automatically makes the other correct.

## State versus runtime versus desired state

These are separate axes:

```text
Service.desired_state
    = what should exist

Deploy.status
    = lifecycle result of one execution attempt

worker ownership
    = who is allowed to mutate that attempt

RuntimeObservation
    = what Docker/Swarm currently reports
```

Examples:

- desired running + runtime missing -> repair/redeploy may be needed;
- desired stopped + runtime running -> queue stop;
- Deploy succeeded + runtime later failed -> reconciliation may mark Service failed;
- runtime healthy + old revision -> runtime is not necessarily the active desired revision.

## Task-start preconditions/postconditions

### Before

- Service must be eligible/queued;
- Deploy must be eligible/pending;
- task id must be current.

### After success

- Service -> DEPLOYING;
- Deploy -> RUNNING;
- task id and heartbeat are stored;
- desired_state is set to running by the execution path.

### After failure

The state tracker commits a terminal state through the ownership boundary. A stale worker cannot overwrite it.

### If cancellation is already set

A pending deployment can become CANCELLED before runtime work starts.

### If ownership is lost

The worker must stop attempting state/runtime mutation.

## Heartbeats

`heartbeat_deploy()` refreshes `worker_heartbeat_at` only while the stored execution_task_id matches.

It is liveness evidence, not ownership itself.

A stale heartbeat does not prove that no worker is still alive; recovery requires external resource identity and a re-check under lock.

## Race scenario: deployment A versus deployment B

1. A acquires Service advisory lock.
2. B attempts the same lock and is rejected/skipped.
3. A builds/applies runtime.
4. If A loses the worker, lock release alone does not grant A future authority.
5. B can later acquire the Service.
6. B becomes active.
7. A's stale completion cannot pass the task-id/active-deploy fence.
8. Reconciliation may recover or fail A based on proven runtime ownership.

### Critical invariant

A worker that started first does not automatically own the right to activate last.

## Race scenario: cancellation versus completion

If cancellation is committed before final completion:

```text
worker -> terminal transition
             ^
             |
     cancellation row lock
```

The StateManager sees `cancel_requested` and redirects the terminal transition to CANCELLED.

The later worker result cannot override it.

## Race scenario: monitor versus worker

The monitor may observe a stale heartbeat.

It must not immediately delete the runtime resource.

For recovery it verifies:

- Deploy still has stale lifecycle state;
- no newer owner has taken the Deploy/Service;
- external resource identity proves association with this deployment.

In legacy mode, “container with canonical name exists” is deliberately insufficient.

## Race scenario: application deployment versus base-image renewal

Case:

```text
BaseRuntimeImage = BUILDING
local image = compatible
```

Application deployment continues using the local image. The renewal owner can continue rebuilding in parallel.

Case:

```text
BaseRuntimeImage = BUILDING
local image = incompatible/missing
```

Application deployment waits for the shared build rather than creating a duplicate.

The wait is bounded by the base-image phase deadline.

## Base-image worker ownership

The base-image row stores task/owner metadata.

A builder may retry, fail terminally, or be superseded.

Every state update is matched against its task id so an old retry cannot mark a new owner's build as failed.

## Retry boundaries

### Application deploy

The Celery task retries only `DeploymentError.recoverable == True`.

Deterministic validation and build errors remain terminal for that attempt.

### Database deploy

Uses bounded retries and `is_retryable_exception()` to identify transient infrastructure conditions.

### Base image

Has its own task retry policy and lifecycle/ownership metadata.

### Why not “retry everything”

A bad Dockerfile, invalid state transition, unsupported runtime or programming bug is not made safer by repeating it.

## Cancellation contract

**Policy:** `application/cancellation.py`

**Persistence:** `infrastructure/django_cancellation.py`

- pending -> immediate terminal cancellation;
- running/rolling back -> set cancellation token and let owner stop/clean;
- terminal/other state -> preserve idempotent historical behavior.

The runtime cleanup is conditional on ownership.

## What this layer must NOT do

Do not:

- hold a DB row lock over Docker build/runtime;
- use Redis lock state as authoritative ownership;
- create a second state machine;
- make the monitor the owner of ordinary deployment cleanup;
- retry based only on “exception happened”;
- clear task ownership before terminal cleanup semantics are safe;
- let tenant configuration choose worker queue/concurrency.

## How to modify this layer

- changing transition legality -> state_machine + state tests;
- changing ownership -> locks + fencing tests;
- changing retry semantics -> task code + common retry/exception tests;
- changing cancellation -> pure policy first, then Django gateway, then runtime cleanup;
- changing queue topology -> settings + Compose + queue contract tests.

## Related code

- `src/config/settings.py`
- `compose.yaml`
- `src/deployments/celery/tasks.py`
- `src/deployments/celery/schedules.py`
- `src/deployments/celery/services/deploy_service.py`
- `src/deployments/celery/services/stop_service.py`
- `src/deployments/core/state/locks.py`
- `src/deployments/core/state/manager.py`
- `src/deployments/common/state_machine.py`
- `src/deployments/common/retry.py`
- `src/deployments/application/cancellation.py`
- `src/deployments/application/context.py`
