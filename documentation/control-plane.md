# Control Plane

## Request path

```text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> Service / Deploy domain
 -> Celery operation
 -> deployments
 -> Docker Engine
```

Django owns authentication, authorization, desired state and durable records. Celery owns asynchronous work. Docker Swarm owns task placement and restart mechanics.

## Celery queues

Deployment-heavy tasks use dedicated queues such as `deployments`, `operations` and `base-images`. Redis is the broker/result/cache infrastructure.

## Beat

Beat schedules service reconciliation, Swarm node synchronization, catalog reconciliation, shell expiry, scheduled messaging and log retention.

Beat is a repair mechanism, not the primary runtime scheduler.

## Databases

The main PostgreSQL database stores control-plane state. Deployment logs can use the separate `deployment_logs` database through `DeploymentLogRouter`.

## Channels

Channels transports realtime events and shell/messaging traffic. WebSockets are delivery paths, never the authoritative state store.
