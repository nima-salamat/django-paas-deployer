# Control Plane

## Request path

~~~text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> Service / Deploy domain
 -> Celery operation
 -> deployments
 -> Docker Engine
~~~

Django owns authentication, authorization, desired state and durable records. Celery owns asynchronous work. Docker Swarm owns task placement and restart mechanics.

## Deployment architecture

Deployment work is described in the canonical [deployments architecture manual](deployments/README.md). Read its worker/state chapter before changing queue routing, locks, retries or cancellation.

## Celery queues

Deployment-heavy tasks use the dedicated queues deployments, operations and base-images. Redis is the broker/result/cache infrastructure.

Current task-to-queue ownership and worker topology are documented in [deployments/06-workers-concurrency-and-state.md](deployments/06-workers-concurrency-and-state.md).

## Beat

Beat schedules service reconciliation, Swarm node synchronization, catalog reconciliation, shell expiry, scheduled messaging and log retention.

Beat is a repair mechanism, not the primary runtime scheduler. Deployment monitor behavior is documented in [deployments/07-reconciliation-and-recovery.md](deployments/07-reconciliation-and-recovery.md).

## Databases

The main PostgreSQL database stores control-plane state. Deployment logs can use the separate deployment_logs database through DeploymentLogRouter. Deployment event flow is documented in [deployments/09-logs-health-rollback-cleanup.md](deployments/09-logs-health-rollback-cleanup.md).

## Channels

Channels transports realtime events and shell/messaging traffic. WebSockets are delivery paths, never the authoritative state store.
