# 07 — Reconciliation and recovery

## Purpose

Deployment execution is not the only source of truth. The system continuously compares desired database state with observed runtime state so worker crashes, missed events and infrastructure restarts can be repaired.

## Two reconciliation layers

The repository contains both:

1. a runtime-neutral decision model in deployments.reconciliation.planner;
2. concrete production monitoring and repair logic in deployments.celery.schedules.

They are related, but the scheduled monitor still contains the concrete Docker/Swarm actions on current master.

Do not describe the pure planner as if every production reconciliation action already flows through it.

## Desired state

The runtime-neutral model is DesiredRuntimeState:

- service_id;
- revision_id;
- desired_state;
- runtime_name;
- required_capabilities;
- metadata.

The production domain contributes this primarily through Service.desired_state and Service.active_revision.

For a running service, the desired revision is the currently authoritative active revision.

## Observed state

Runtime adapters return RuntimeObservation containing:

- RuntimeIdentity;
- observed runtime status;
- runtime resource id;
- desired and ready replica counts;
- observed revision id when known;
- per-task observations;
- timestamp and details.

Observed state describes infrastructure reality. It does not rewrite desired state merely because it is different.

## Pure reconciliation planner

ReconciliationPlanner.decide() can return:

- CONVERGED;
- CREATE;
- UPDATE;
- STOP;
- REPAIR;
- BLOCKED;
- MANUAL_INTERVENTION.

It checks runtime capabilities and availability before choosing an action.

Important fail-closed rule: when a runtime resource exists but its managed revision identity is unknown, the planner returns MANUAL_INTERVENTION instead of silently adopting it.

## Scheduled monitor

deployments.celery.schedules.monitor_services() performs two broad scans.

### Active deployments

It watches pending, running and rolling-back Deploy rows for:

- phase timeout;
- cancellation;
- runtime progress;
- stale worker recovery;
- rollback completion/failure.

### Active services

It checks queued, deploying, running, stopping and legacy-succeeded Service rows against runtime state.

It can:

- queue desired-state stop operations;
- requeue orphaned PENDING deployments;
- mark dead runtimes failed;
- promote legacy SUCCEEDED rows to RUNNING;
- finalize stopping;
- recover stale deployments where ownership is provable;
- reconcile stale base-image builds.

## Monitor scheduler gate

Beat can pulse the monitor frequently. monitor_services uses Redis to record last_run and a lightweight lock.

The effective monitor interval and batch size come from operator settings.

Redis here is coordination only. The database remains authoritative for Service/Deploy state.

If the scheduler gate cannot be used, the monitor does not reinterpret that as a deployment-state failure.

## Orphaned queued deployment recovery

A deployment may commit its DB transaction while the broker is temporarily unavailable before the task is delivered.

_monitor recovery detects PENDING Deploy + QUEUED Service rows older than the stale threshold and can re-enqueue them.

The recovery path:

1. increments a per-deployment Redis attempt counter;
2. stops after max_recovery_attempts;
3. chooses application vs database task from the platform;
4. submits a new task id;
5. updates Deploy execution_task_id and Service.task_id only while the rows remain pending/queued.

This makes broker interruption recoverable without an unbounded duplicate-task loop.

## Stale worker recovery

### Swarm mode

The monitor can recover a stale RUNNING deployment only when it can prove:

- the managed Swarm service exists;
- the expected single running task exists;
- deployment identity labels match the stale Deploy;
- the Deploy is still RUNNING;
- no newer active Deploy has taken ownership.

Only then can it materialize/activate the revision and mark the deployment succeeded.

### Legacy container mode

The canonical container name may still refer to the previous release while a replacement image is being built.

Therefore “container is running” is not proof that the stale deployment succeeded.

For replacement/container-start/health stages, the monitor requires deployment ownership labels before removing a stale replacement and attempting previous-resource restoration.

For pre-container or ambiguous worker loss, recovery fails closed rather than guessing.

## Desired-state repair

When desired_state=stopped and runtime is still running, reconciliation can queue the stop task.

When desired_state=running and no runtime exists, reconciliation may reuse the active Deploy/revision where the current eligibility checks permit it.

Reconciliation does not invent a new revision.

## Runtime drift

Current monitor logic handles:

- Swarm service/task loss;
- Docker container loss in the legacy mode;
- runtime not running after a deployment;
- stopped services that should be running;
- running resources that should be stopped.

The runtime-neutral planner additionally models UPDATE when observed revision differs from desired revision.

## Timeouts

A deployment timeout marks cancel_requested and leaves external cleanup to the owning worker.

This prevents a monitor race in which the monitor deletes resources while the original deployment worker is still cleaning them.

Base-image BUILDING rows also have a separate operator-owned lifecycle timeout. An expired base build can be marked FAILED so waiters are released.

## Swarm infrastructure sync

sync_swarm_infrastructure calls the concrete Swarm node synchronizer when Swarm is enabled.

It updates operator-visible SwarmCluster and SwarmNode records independently from application runtime services.

## External failures

The recovery model explicitly covers:

- worker crash;
- Docker daemon restart/unavailability;
- Redis/Celery interruption;
- missed deployment/event messages;
- externally removed or modified managed Swarm resources;
- stale DB execution state.

Recovery is always constrained by resource identity and lifecycle ownership.

## Idempotence and repair safety

A reconciliation repair must be safe to repeat.

It must not:

- activate a stale revision;
- silently adopt an unmanaged same-name runtime;
- overwrite a newer active deployment;
- turn observed image/runtime data into desired configuration;
- mutate tenant policy to make infrastructure converge.

## What reconciliation must NOT own

Reconciliation decides whether reality converges. The runtime adapter/backend owns Docker calls.

Reconciliation must not become a second implementation of platform detection, application image building or tenant configuration resolution.

## Related code

- src/deployments/reconciliation/planner.py
- src/deployments/celery/schedules.py
- src/deployments/celery/monitoring/actions.py
- src/deployments/celery/monitoring/policies.py
- src/deployments/runtime/observations.py
- src/deployments/runtime/swarm/adapter.py
- src/deployments/core/swarm.py
