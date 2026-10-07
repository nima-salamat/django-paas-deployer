# 07 — Reconciliation and recovery

## Purpose

Reconciliation handles the gap between what the database says should exist and what Docker/Swarm actually reports.

The architectural split is:

```text
desired state
    +
runtime observation
    ->
reconciliation decision
    ->
runtime action
```

**Decision and execution are intentionally separate.**

## Current implementation status

Two layers coexist:

- `ReconciliationPlanner` is a pure, runtime-neutral decision model.
- `deployments.celery.schedules` builds desired/observed inputs; actionable Swarm repair goes through `ReconciliationExecutor` -> `RuntimeContract` -> `SwarmRuntimeAdapter`.

The planner is an architectural contract and test target, not yet the only production reconciliation engine.

## DesiredRuntimeState

**Path:** `reconciliation/planner.py`

Contains:

- service id;
- desired revision id;
- desired running/stopped state;
- runtime name;
- required capabilities;
- metadata.

### Why

A repair decision must use a stable representation of intent rather than rereading many mutable model fields inside each rule.

## RuntimeObservation

**Path:** `runtime/observations.py`

An observation contains:

- identity;
- status;
- runtime id;
- desired/ready replicas;
- observed revision id;
- task observations;
- timestamp/details.

### Why identity is part of observation

Runtime state without identity is unsafe for destructive repair.

## ReconciliationPlanner

**Path:** `reconciliation/planner.py`

### Called by

Pure contract tests and future runtime-neutral reconciliation composition.

### Input

DesiredRuntimeState + RuntimeObservation + RuntimeSelection.

### Output

ReconciliationDecision.

### Decision meanings

- CONVERGED: observed state already matches desired state.
- CREATE: desired running resource is missing.
- UPDATE: observed revision differs from desired revision.
- STOP: runtime exists but desired state is stopped.
- REPAIR: resource exists but is unhealthy/not ready.
- BLOCKED: backend capability/availability prevents safe execution.
- MANUAL_INTERVENTION: identity/policy is too ambiguous to repair automatically.

### Preconditions

Runtime capabilities and availability are checked first.

### Fail-closed rule

If desired revision is known but observed runtime revision is unknown, the planner does **not** assume the same-name resource is the desired resource.

It returns MANUAL_INTERVENTION.

## Why reconciliation must not “helpfully adopt” resources

Consider:

```text
desired revision = B
runtime service name exists
revision label = missing
```

Possible explanations include:

- unmanaged external service;
- old resource;
- partially updated resource;
- label drift.

Automatically adopting it would turn ambiguity into state corruption.

The architecture therefore prefers manual intervention over unsafe convergence.

## Scheduled monitor

**Path:** `celery/schedules.py::monitor_services`

### Entry

Celery Beat pulses the task every 5 seconds in current settings.

The task applies an operator-configured interval through a Redis scheduler gate so frequent Beat pulses do not imply full reconciliation every 5 seconds.

### Two scans

#### Active Deployments

Checks:

- PENDING/RUNNING/ROLLING_BACK Deploy rows;
- timeout budgets;
- cancellation state;
- runtime progress;
- stale worker recovery.

#### Active Services

Checks:

- QUEUED;
- DEPLOYING;
- RUNNING;
- STOPPING;
- legacy SUCCEEDED

against runtime reality.

## Scheduler gate versus lifecycle state

Redis stores:

- last monitor run;
- monitor lock;
- bounded recovery attempt counters.

These keys coordinate work.

They do not replace Service/Deploy lifecycle state.

## Orphaned queued deployment

### Failure scenario

```text
DB transaction commits Deploy=PENDING
        |
Celery publish is interrupted
        |
no worker receives task
```

The DB state remains valid.

The monitor can later detect an old PENDING/QUEUED pair and requeue it with bounded attempts.

### Why

Broker interruption should not force the API transaction to roll back durable deployment intent.

## Stale worker recovery

### Swarm mode

A stale RUNNING deploy can be recovered as successful only when:

1. Swarm service exists;
2. one expected task is running;
3. service deployment label matches the Deploy;
4. Deploy is still RUNNING;
5. no newer active deployment has superseded it.

Only then does recovery materialize/activate the revision and mark success.

### Legacy mode

A canonical container name can refer to the previous release during build.

Therefore:

```text
running container
   !=
proof that stale Deploy succeeded
```

For container creation/start/health phases, recovery first proves the resource belongs to the stale deployment through the deployment identity label before removing/restoring it.

Ambiguous pre-container worker loss is failed closed.

## Desired-state repair

### Desired stopped

If runtime is still running, reconciliation queues the stop operation.

### Desired running

If no runtime exists and an eligible active Deploy/revision exists, reconciliation can queue deployment.

It does not invent a new desired revision.

## Timeout ownership

When a deployment times out, the monitor marks `cancel_requested`.

It does **not** become the ordinary runtime cleanup owner.

The worker that still owns execution performs cancellation cleanup.

### Why

A monitor and deployment worker running simultaneously must not both delete/restore the same resource.

## Base-image recovery

The monitor detects BUILDING BaseRuntimeImage rows that exceed the operator timeout.

It changes the row to FAILED with diagnostics, clears build ownership, and releases waiters.

A later rebuild can safely claim the resource again.

## Swarm infrastructure synchronization

`sync_swarm_infrastructure` synchronizes operator-visible SwarmCluster/SwarmNode metadata when Swarm is enabled.

This is separate from application runtime reconciliation.

## Recovery invariants

1. No stale worker can activate over a newer active deployment.
2. No unmanaged same-name resource is silently adopted.
3. No ambiguous external resource is deleted without ownership proof.
4. Desired state is not overwritten by observed state.
5. Reconciliation actions are safe to repeat.
6. Runtime unavailability blocks destructive action rather than pretending convergence.

## Problem navigation

| Symptom | Start | Then | Why |
|---|---|---|---|
| resource missing | planner + monitor | runtime inspect/apply | distinguish repair from new deploy |
| wrong revision running | planner | identity labels + active revision | revision drift is not just process liveness |
| stale worker | monitor recovery | state manager + runtime labels | ownership must be proved |
| monitor falsely marks failure | monitor policy/actions | Deploy state + runtime stage | pre-container grace rules matter |
| external service adopted | planner | runtime identity/labels | unknown identity must fail closed |
| monitor requeues repeatedly | orphan recovery | recovery Redis key + task state | bounded recovery prevents loops |

## What reconciliation must NOT do

Do not:

- call platform detectors to rebuild application policy;
- change tenant configuration to make runtime converge;
- treat same-name as ownership;
- delete resources without identity proof;
- make observed state authoritative over desired state;
- become a second implementation of application deployment planning.

## Related code

- `src/deployments/reconciliation/planner.py`
- `src/deployments/celery/schedules.py`
- `src/deployments/celery/monitoring/actions.py`
- `src/deployments/celery/monitoring/policies.py`
- `src/deployments/runtime/observations.py`
- `src/deployments/runtime/registry.py`
- `src/deployments/runtime/swarm/adapter.py`
- `src/deployments/core/swarm.py`
