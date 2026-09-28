# Control Plane

## Request path

~~~text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> domain app (users/auth/services/deploy/etc.)
 -> Celery
 -> deployments
 -> Docker Engine / Swarm
~~~

Use [apps/README.md](apps/README.md) to locate the owning application and [deployments/README.md](deployments/README.md) for runtime execution.

## Durable authority

Django model state is the durable control-plane authority for desired state, ownership, provenance and workflow state. Redis, Celery task ids and WebSocket events are coordination/transport mechanisms and do not replace that authority.

## Workers

Deployment-related worker topology, queues, locks, task ownership, retries and cancellation are canonical in [deployments/06-workers-concurrency-and-state.md](deployments/06-workers-concurrency-and-state.md).

## Reconciliation

Scheduled reconciliation compares durable desired state against runtime/worker observations. The detailed recovery contract is [deployments/07-reconciliation-and-recovery.md](deployments/07-reconciliation-and-recovery.md).

## Databases

The primary PostgreSQL database stores control-plane/domain state. DeployLog may use a dedicated PostgreSQL database; see [apps/deploy/models.md](apps/deploy/models.md) and [deployments/09-logs-health-rollback-cleanup.md](deployments/09-logs-health-rollback-cleanup.md).

## Redis and Channels

Redis supports Celery transport/results and selected coordination/cache. Channels transports realtime notifications. Neither transport is the source of durable business state.
