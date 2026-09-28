# 09 — Logs, health, rollback and cleanup

## Purpose

Keep execution diagnostics and safety-sensitive cleanup in one place so a failure can be traced from worker log to Deploy state to runtime resource.

## Event pipeline

~~~text
DeploymentOrchestrator / DBDeployer
          |
          v
DeploymentLogger
          |
          v
DBAndChannelEventSink
      |        |
      v        v
 DeployLog   Deploy row/progress
      |
      v
Channels group deploy_<id>
      |
      v
DeploymentConsumer / UI
~~~

## DeploymentLogger

deployments.core.deployment_logger.DeploymentLogger emits DeploymentEvent values containing:

- stage;
- message;
- level;
- progress;
- structured details.

It writes to the Python logger and optionally calls an EventSink.

Because the default Celery formatter may render only message text, DeploymentLogger renders high-signal diagnostic fields into the worker log message too.

## Event sink

DBAndChannelEventSink in core/sink.py:

1. writes DeployLog;
2. synchronizes Deploy progress, stage and status message;
3. broadcasts to the Channels group for the deployment UI.

The sink is best-effort. A sink/database/channel failure must not become a false deployment failure.

Terminal state transitions from the sink still pass through StateManager.

Low-value Docker build stream noise is filtered/throttled for persistence and WebSocket delivery while warnings/errors and terminal events are preserved.

## Deployment log database

DeployLog is designed for the separate deployment-log database.

It stores deployment/service ids as scalar fields so cross-database foreign-key constraints are not required.

compose.yaml defines deployment-log-db as a separate PostgreSQL service.

## Health versus readiness

These concepts must stay distinct.

**Runtime readiness** means the runtime resource satisfies the backend's ready invariant.

**Application health** means the application/container health policy reports healthy.

In Swarm mode, runtime readiness currently requires a running task for each enabled process. The legacy container runtime can additionally use DockerHealthChecker HTTP/path checks.

“Container exists” is not equivalent to “deployment is ready”.

## Health failure

A readiness or health timeout should preserve:

- deployment stage;
- runtime resource identity;
- latest task/container status;
- health path/expected status when configured;
- underlying Docker/application error when available.

A health failure after image build is not evidence that the image build itself failed.

## Rollback ownership

Rollback differs by runtime mode.

### Legacy container runtime

DeploymentOrchestrator can capture a ContainerSnapshot before replacing the previous resource.

The replacement sequence retains the old container long enough to restore it if the new release cannot become ready.

On rollback:

1. stop/remove the replacement as needed;
2. restore the previous owned resource;
3. explicitly record rollback success/failure.

Rollback failure is not treated as successful deployment cleanup.

### Runtime-contract seam

The framework-neutral lifecycle executor can invoke RuntimeContract.rollback() using an explicit rollback_plan.

This is a migration seam. The current main application path still uses concrete DeploymentOrchestrator rollback mechanics.

## Activation is before destructive cleanup

The safety boundary is:

~~~text
build
  -> apply runtime
  -> readiness
  -> activate revision
  -> remove old resources
~~~

Before activation, cleanup must not destroy the only known-good release.

After activation, old managed resources can be removed.

## Cleanup manager

CleanupManager can remove explicitly owned failed containers/images.

Its prune_dangling_images() intentionally does not perform host-wide Docker pruning. A deployment worker shares the daemon with unrelated workloads, so global garbage collection is not ownership-safe.

Host-wide Docker GC belongs to an operator-managed maintenance action.

## Persistent volume safety

Persistent volumes are separate resources with ownership/accounting.

A failed application deploy does not automatically imply that its persistent volume may be deleted.

Released-volume reclamation is a separate operations-queue task.

Database force-reinit is a distinct explicit destructive operation and is documented in 10-database-deployments.md.

## Failure artifact preservation

A failed deployment should retain enough evidence to answer:

- which deployment/revision failed;
- which phase failed;
- which base/application image was selected;
- what runtime resource was affected;
- whether rollback happened;
- whether rollback succeeded;
- what the first meaningful Docker/application error was.

Do not design failure cleanup in a way that destroys the only diagnostic artifact before the event/state is recorded.

## WebSocket behavior

The event sink throttles duplicate/non-critical build events but sends errors and terminal events immediately.

Channel/database delivery errors are logged and ignored by the deployment execution path.

## What this layer must NOT do

Do not:

- use UI logging success as proof of deployment success;
- globally prune the Docker daemon from a deployment worker;
- delete persistent volumes solely because a container failed;
- treat a healthy old resource as proof that the new revision was activated;
- make event delivery a prerequisite for lifecycle completion.

## Related code

- src/deployments/core/deployment_logger.py
- src/deployments/core/sink.py
- src/deployments/core/health.py
- src/deployments/core/rollback.py
- src/deployments/core/cleanup.py
- src/deployments/core/volumes.py
- src/deployments/core/volume_storage.py
- src/deployments/celery/tasks.py
