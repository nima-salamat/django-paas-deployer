# 09 — Logs, health, rollback and cleanup

## Purpose

These concerns cross the main lifecycle but have different responsibilities. The architecture keeps evidence production, readiness, rollback and destructive cleanup separate so a failure can be diagnosed without destroying the last known-good state.

## Event path

```text
orchestrator / DBDeployer
       |
       v
DeploymentLogger
       |
       v
DjangoDeploymentState / DBAndChannelEventSink
       |
       +--> DeployLog database
       +--> Deploy progress/stage/status
       +--> Channels group deploy_<id>
```

## DeploymentLogger

**Path:** `core/deployment_logger.py`

### Called by

Orchestrator, runtime/build components and database deployer via an EventSink.

### Contract

Create a DeploymentEvent containing stage/message/level/progress/details and:

- write a Python log entry;
- forward to an optional sink.

### Why diagnostics are rendered into log text

The Celery worker formatter may display only `message`. High-signal Docker fields are therefore rendered in the message as well as structured sink details.

### Failure behavior

Sink exceptions are swallowed/sampled. Observability failure must not become a runtime failure.

## DBAndChannelEventSink

**Path:** `core/sink.py`

### Responsibilities

1. persist DeployLog;
2. update Deploy stage/progress/status message;
3. broadcast to the Channels deployment group.

### Preconditions

Deployment id is known.

### Postcondition

Best-effort evidence delivery. It is not the authority for external runtime success.

Terminal status changes use StateManager.

### What it must not do

It must not make “the UI received the event” a prerequisite for deployment completion.

## DeployLog storage boundary

DeployLog uses scalar Deploy/Service ids because logs may live in a separate PostgreSQL database.

The Compose stack contains `deployment-log-db`.

Do not introduce cross-database Django foreign keys into the log store.

## Health and readiness

### Runtime readiness

Backend-specific statement that infrastructure has become usable.

### Application readiness

Application-level condition, such as:

- Docker HEALTHCHECK;
- HTTP endpoint returning an expected status.

### Legacy container health

`DockerHealthChecker.wait_until_healthy()`:

- repeatedly checks container state;
- may require a Docker health status;
- can require an application HTTP path;
- requires at least three consecutive running polls by default when no healthcheck/path is available.

### Important non-equivalence

```text
container exists
   !=
container ready
   !=
application ready
   !=
revision active
```

Do not use existence as success.

## How readiness is used

**Caller:** orchestrator.

**Precondition:** runtime resource has been applied.

**Output:** readiness evidence or HealthCheckError/RuntimeOperationError.

**Next:** activation.

**Modification rule:** change readiness semantics in health/runtime code and update readiness contract tests; do not weaken activation to compensate.

## Swarm readiness

Current Swarm runtime reports ready when desired and running replica counts satisfy the backend invariant.

A task failure/rejection produces a runtime error with task details.

Application-level HTTP semantics are separate.

## Rollback

### Legacy container path

**Path:** `core/rollback.py`

Before replacing an active container, the orchestrator can capture `ContainerSnapshot`.

The snapshot preserves enough information to restore the previous runtime resource:

- image;
- environment;
- networks;
- volumes;
- read-only state;
- command/entrypoint;
- runtime metadata/labels;
- resource settings.

### Failure flow

```text
previous resource
    -> snapshot
    -> replacement
    -> start
    -> readiness fails
    -> rollback restore
```

Rollback errors are surfaced as `RollbackError`.

### New lifecycle contract path

`DeploymentLifecycleExecutor` can call `RuntimeContract.rollback()` with an explicit rollback_plan.

This is a migration seam, not the only current production rollback path.

## Why rollback is before terminal success

A runtime that failed readiness is not a new active release.

When rollback succeeds, the system can report failure plus rollback performed.

When rollback fails, it reports failure plus rollback_failed and preserves diagnostics for operator intervention.

## Cleanup

**Path:** `core/cleanup.py`

### Owns

Explicitly owned deployment resource cleanup.

### Does not own

Host-wide Docker garbage collection.

`prune_dangling_images()` intentionally returns without global prune.

### Why

The deployment worker shares the Docker daemon with unrelated services. It cannot prove ownership of arbitrary dangling images.

## Cleanup ordering

Safe sequence:

```text
build
 -> apply
 -> readiness
 -> activate
 -> remove old owned release
 -> release leases
```

Before activation, preserve the previous known-good release.

## Service deletion and log ownership

`Service` is the deletion boundary for service-scoped observability data. Because `DeployLog` and the runtime log models live in the separate deployment-log database and use scalar `service_id` references, they are explicitly removed by the Service deletion signal rather than by Django foreign-key cascade.

Deployment deletion is different: it removes deployment-owned source artifacts and durable deployment execution records, but it does not define the Service lifecycle or stop an active runtime by itself.

## Persistent volume cleanup

A failed application container is not sufficient reason to delete persistent data.

Volume release/reclamation is separately scheduled through `reclaim_released_volumes`.

Database `force_reinit` is explicit destructive behavior and is handled by the database deployment path.

## Cancellation cleanup

For the newer lifecycle executor:

- cancellation checks ownership;
- if a runtime handle exists and ownership remains current, runtime stop/remove may run;
- if ownership is lost, cleanup is skipped to avoid deleting a newer owner's resource.

The current concrete orchestrator also checks cancellation between stages.

## Failure evidence contract

At terminal failure, preserve enough data to identify:

- Deploy/revision;
- lifecycle stage;
- application/base image reference;
- runtime resource identity;
- underlying error/code/category;
- rollback status;
- relevant container/task state.

### Why evidence precedes broad cleanup

A clean filesystem with no diagnostic log is not operationally recoverable.

## Problem navigation

| Symptom | Start | Why |
|---|---|---|
| UI has no deploy logs | sink + log DB routing | event delivery/storage |
| worker log is generic | DeploymentLogger | diagnostic rendering |
| container running but deploy fails health | health checker | readiness, not image |
| new resource fails and old disappeared | rollback/orchestrator | cleanup ordering |
| volume vanished after failure | volumes + cleanup | persistence is separately owned |
| stale worker cleanup is dangerous | lifecycle + monitor | ownership fence |

## What this layer must NOT do

Do not:

- equate event delivery with execution success;
- globally prune Docker from a deployment;
- delete persistent data because a release failed;
- declare activation before readiness;
- silently swallow rollback failure.

## Related code

- `src/deployments/core/deployment_logger.py`
- `src/deployments/core/sink.py`
- `src/deployments/core/health.py`
- `src/deployments/core/rollback.py`
- `src/deployments/core/cleanup.py`
- `src/deployments/core/volumes.py`
- `src/deployments/core/volume_storage.py`
- `src/deploy/deployment_state.py`
