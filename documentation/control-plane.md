# Control Plane

## Request path

```text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> domain app (users/auth/services/deploy/etc.)
 -> Celery
 -> deployments
 -> Docker Engine / Swarm
```

Use [apps/README.md](apps/README.md) to locate the owning application and [apps/deployments/README.md](apps/deployments/README.md) for runtime execution.

## Durable authority

Django model state is the durable control-plane authority for desired state, ownership, provenance and workflow state. Redis, Celery task ids and WebSocket events are coordination/transport mechanisms and do not replace that authority.

## Workers

Deployment-related worker topology, queues, locks, task ownership, retries and cancellation are canonical in [deployments/execution/06-workers-concurrency-and-state.md](apps/deployments/execution/06-workers-concurrency-and-state.md).

## Deployment execution authority

~~~text
Service
 -> ServiceRevision
 -> Release
 -> Deploy / DeploymentAttempt
 -> DeploymentLifecycleExecutor
 -> RuntimeContract
 -> SwarmRuntimeAdapter
 -> SwarmRuntime
 -> readiness
 -> canonical activation
~~~

The activation boundary updates `Service.active_revision`; runtime observations
never become desired state. Deployment ownership continues to use durable worker
identity, heartbeat and lifecycle-generation fencing.

## Reconciliation

Scheduled reconciliation compares durable desired state against runtime
observations. The pure `ReconciliationPlanner` produces a decision and the
generation-aware `ReconciliationExecutor` is the runtime repair boundary.
Unknown or unowned runtime identity is not destructively adopted.


## Databases

The primary PostgreSQL database stores control-plane/domain state. DeployLog may use a dedicated PostgreSQL database; see [apps/deploy/models.md](apps/deploy/models.md) and [deployments/execution/09-logs-health-rollback-cleanup.md](apps/deployments/execution/09-logs-health-rollback-cleanup.md).

## Redis and Channels

Redis supports Celery transport/results and selected coordination/cache. Channels transports realtime notifications. Neither transport is the source of durable business state.
