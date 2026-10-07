# 03 — Execution lifecycle

## Purpose

This is the operational map of one application deployment. Read it before
changing execution, activation, cancellation, rollback or runtime behavior.

## Production call chain

~~~text
deploy()
  |
  v
DeployService.execute()
  |
  +--> PostgreSQL advisory lock
  +--> StateManager ownership/fencing
  |
  v
ensure_revision_for_deploy()
  |
  v
_process_deployment()
  |
  +--> revision snapshot + normalized configuration
  +--> platform detection + policy validation
  |
  v
native DeploymentPlan
  |
  v
DeploymentLifecycleExecutor
  |
  +--> strategy.plan()
  |      +--> base-image resolution
  |      +--> Dockerfile generation
  |      +--> application artifact build
  |      +--> immutable BuildArtifact
  |      +--> immutable Release
  |
  +--> RuntimeContract.apply()
  +--> RuntimeContract.wait_ready()
  +--> canonical activation / success
  |
  v
DjangoDeploymentState.finish()
  |
  v
terminal Deploy + durable event
~~~

The native Swarm path never constructs DeploymentOrchestrator. The lifecycle
executor is the production lifecycle owner.

The build step still uses the existing Dockerfile generator and image manager,
but the resulting artifact is promoted into a durable BuildArtifact before
runtime application.

## Entry: Celery task

**Module:** `deployments/celery/tasks.py::deploy`

### Preconditions

- Deploy id exists;
- task is not already cancelled;
- database platform guard has either routed DB work or determined application path.

### Action

Calls `DeployService.execute()` with the Celery task id as execution owner.

### Retry boundary

Permanent errors are logged without retry. Only `DeploymentError` instances carrying recoverable=True are retried. Unknown Python errors are translated to non-recoverable platform errors.

### Why the task boundary matters

Celery is where asynchronous retry/acknowledgement semantics belong. It should not become a second deployment state machine.

## DeployService.execute()

**Module:** `celery/services/deploy_service.py`

### Called by

Application Celery deploy task and recovery requeue.

### Preconditions

Deploy exists and has a Service.

### Action

1. obtains Service id;
2. acquires per-Service PostgreSQL advisory lock;
3. enters `_execute_locked()`.

### Why advisory lock exists

Image builds and Docker runtime operations outlive a transaction. A row lock released before those operations would allow a second deployment to start against the same Service.

### Postcondition

Either the lifecycle has been completed by the owner or execution was skipped/failed under the ownership contract.

## State start

**Module:** `core/state/manager.py`, `celery/service_status.py`

### Preconditions

Service is in the expected queued/eligible state and task ownership matches.

### Transition

```text
Service  QUEUED -> DEPLOYING
Deploy   PENDING -> RUNNING
```

### Side effect

The Deploy receives task ownership and heartbeat timestamps.

### Why

This is the authoritative handoff from async queue delivery to active deployment execution.

## Revision boundary

`ensure_revision_for_deploy()` is called before the deployment uses mutable configuration as an execution source.

### Postcondition

`deploy_item.revision_id` exists and can materialize the executable snapshot.

If revision creation fails, no runtime execution should continue.

## _process_deployment()

This is the compatibility-heavy application composition layer.

It:

1. materializes revision config;
2. normalizes profile/config;
3. uses Service Plan platform as the execution-family authority;
4. refines supported framework aliases;
5. validates scoped customizations;
6. gets Dockerfile text;
7. runs `DeploymentValidator.validate_for_deploy()`;
8. uses a legacy restart-only fast path only when Swarm is disabled;
9. otherwise enters `_execute_orchestrator()`.

### Why this layer exists

It is the current bridge between service/revision semantics and the legacy concrete orchestrator. It is not the long-term runtime contract itself.

## _execute_orchestrator()

This layer combines the final resolved runtime graph and compatibility DTO.

Important inputs:

- Service Plan CPU/RAM;
- operator build resource policy;
- revision runtime graph;
- health/readiness settings;
- endpoints/networks/volumes;
- application image tag;
- activation callback.

### Important ownership rule

The deployment constructs the configuration passed to the orchestrator once and passes it explicitly. Downstream code must not secretly reparse mutable `Deploy.config` to discover a different policy.

## DeploymentOrchestrator.deploy()

**Module:** `core/orchestrator.py`

### Called by

`core/deploy.py::Deploy.deploy_result()` / deploy facade.

### Preconditions

A complete `DeploymentConfig` is available and worker ownership/cancellation is still valid.

### Stages

1. validation and initial cancellation;
2. ZIP/build-context conversion;
3. project extraction/detection;
4. base-image resolution;
5. application phase start;
6. Dockerfile generation;
7. legacy snapshot if Swarm is disabled;
8. application image build;
9. network/volume preparation;
10. runtime apply;
11. readiness;
12. activation callback;
13. cleanup.

### Postcondition

Returns a `DeploymentResult` describing success, failure, cancellation and rollback state. It does not by itself define which revision is authoritative; activation callback does.

## Base-image phase

The orchestrator calls `ensure_base_images()`.

### Preconditions

The platform/runtime version is known enough to derive BaseImageSpec.

### Output

Usable base image refs, potentially after cache reuse or dedicated worker build.

### Timing contract

The base-image wait has a separate phase deadline. When it becomes ready, application deployment receives a fresh application budget.

## Application image

After base-image resolution, the orchestrator renders/builds the deployment-specific application image.

### Important distinction

A successful application image is not yet a successful deployment.

No Service activation should happen until runtime readiness succeeds.

## Runtime application

### Swarm mode

`_deploy_swarm_runtime()` delegates to `SwarmRuntime` and process application.

### Runtime handle contract

A successful runtime apply must return a `RuntimeHandle`. The handle is the stable identity used by readiness, cancellation cleanup and rollback. If apply reports success without a handle, lifecycle execution fails before readiness or activation with `runtime_handle_missing`.

This prevents the lifecycle from guessing which external resource it owns from a name or from mutable service state.

### Legacy mode

When Swarm is disabled, the orchestrator uses container snapshot/rename/replace behavior.

### Why runtime is late

The application image/build decisions are complete before external runtime mutation. This reduces the window in which a failed build can disturb the currently active workload.

## Readiness

Readiness occurs after runtime application.

### Swarm

Current Swarm readiness is satisfied by the runtime service reaching one running task per enabled process.

### Legacy container

`DockerHealthChecker.wait_until_healthy()` may require:

- Docker health status;
- repeated running polls when no healthcheck exists;
- application HTTP status when a path is configured.

### Postcondition

Only a successful readiness result is allowed to enter activation.

## Activation

**Caller:** the callback created in `DeployService._execute_locked()`.

### Preconditions

- runtime readiness succeeded;
- worker still owns execution;
- Service row can be locked.

### Algorithm

1. lock Service;
2. resolve current active deployment;
3. compare with captured `previous_deploy_id`;
4. reject if another deployment already became active;
5. call `activate_revision_locked()`;
6. set desired_state=running.

### Why compare previous_deploy_id

Without the compare-and-lock, deployment A could start first, deployment B could become active later, and A could then overwrite B's authority after a long build.

### Postcondition

Service.active_revision points to the newly activated revision and selected_deploy is updated only as a compatibility projection.

## Cleanup

Cleanup starts after activation for destructive “remove old release” operations.

### Safe invariant

Before activation, a failed deployment must not remove the only known-good previous release.

### Global Docker cleanup

Not owned by an individual deployment. `CleanupManager.prune_dangling_images()` intentionally performs no global prune.

## State finalization

**Module:** `deploy/deployment_state.py::DjangoDeploymentState`

### Called by

DeployService after orchestrator result and in exception paths.

### Preconditions

The worker computes a result and current ownership can be checked.

### Postcondition

Owned terminal transitions are committed through `StateManager.transition_deploy_terminal_if_owned()`.

A stale worker cannot overwrite a newer terminal outcome.

## State machine: meaning and allowed flow

| State | Meaning | Who enters | Expected next | Must not happen |
|---|---|---|---|---|
| PENDING | queued but not executing | request/re-execution | RUNNING, CANCELLED, FAILED | runtime mutation without owner |
| RUNNING | this worker is executing | task start | SUCCEEDED, FAILED, CANCELLED, ROLLING_BACK | assume runtime is already healthy |
| ROLLING_BACK | restoring previous release | failure recovery | ROLLED_BACK or FAILED | declare success before restore |
| SUCCEEDED | deployment completed/activated | successful lifecycle | PENDING only by explicit re-execution | transition directly to FAILED |
| FAILED | execution failed | failure path | PENDING by explicit retry/re-execution | silently turn into success |
| CANCELLED | operator cancellation won | cancel path | PENDING only by explicit re-execution | resurrect through stale Celery retry |
| ROLLED_BACK | previous release restored | rollback path | PENDING by explicit re-execution | treat as new revision active |

Service state is a separate state machine and is intentionally only aligned by lifecycle code.

## Cancellation

There are two paths.

### Before worker execution

`PENDING -> CANCELLED` can be committed immediately.

### During execution

```
cancel_requested = true
       |
       v
worker observes at safe boundary
       |
       v
DeploymentCancelled
       |
       v
owned runtime stop/remove where safe
       |
       v
CANCELLED
```

### Race guarantee

The state manager re-checks cancellation under the Deploy row lock. A cancellation committed before completion therefore wins over a late success.

## Rollback semantics

Legacy container rollback relies on a pre-mutation `ContainerSnapshot`.

The newer lifecycle executor supports a plan-level `rollback_plan` through RuntimeContract.

These are two currently coexisting mechanisms.

### Failure postconditions

- rollback success -> failure can be reported with rollback performed;
- rollback failure -> failure is preserved and operator intervention may be required;
- no previous release -> rollback cannot restore an older image.

## Interruption

If the worker crashes:

- no later worker may assume its runtime side effects are safe to delete;
- reconciliation must verify external identity before cleanup or recovery;
- the existing old canonical container in legacy mode is not evidence that the crashed deploy succeeded.

## How to modify the lifecycle safely

Change the first layer that owns the behavior.

Do not:

- add Docker retry policy to Service;
- activate inside runtime code;
- change lifecycle status with a direct assignment;
- let cleanup run before activation without an ownership proof;
- infer success from a same-name running resource.

## Related code

- `src/deployments/celery/tasks.py`
- `src/deployments/celery/services/deploy_service.py`
- `src/deploy/deployment_state.py`
- `src/deployments/core/orchestrator.py`
- `src/deployments/core/state/manager.py`
- `src/deployments/common/state_machine.py`
- `src/services/revisioning.py`


## Ready-to-Deploy entry point

A catalog installation reaches this lifecycle only after `ApplicationInstanceService` has created a normal child `Deploy`. The catalog coordinator owns dependency readiness and dispatch fencing, while this subsystem owns revision compilation, DB/app routing, build/runtime execution, readiness and terminal Deploy state. A catalog database child therefore follows the existing DBDeployer path rather than the APP image-build path.
