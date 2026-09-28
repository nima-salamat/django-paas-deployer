# Control Plane

## Request path

~~~text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> Service / Deploy domain
 -> Celery
 -> deployments
 -> Docker Engine / Swarm
~~~

Django owns authorization, durable records and desired service state. Celery owns asynchronous execution. Docker/Swarm owns runtime scheduling.

## Deployment architecture

For deployment work, use the canonical [deployment architecture manual](deployments/README.md).

The [workers/concurrency/state guide](deployments/06-workers-concurrency-and-state.md) is the source for queue topology, locks, task ownership, retries and cancellation.

## Beat

Current deployment-related schedules include:

- service/deployment reconciliation pulse;
- Swarm infrastructure synchronization;
- retained-volume reclamation.

Beat triggers repair work. It is not the authority for desired state or runtime lifecycle.

## Databases

The main PostgreSQL database stores control-plane state.

Deployment logs can use a separate PostgreSQL database. See [deployments/09-logs-health-rollback-cleanup.md](deployments/09-logs-health-rollback-cleanup.md).

## Redis

Redis is used for Celery transport/results and selected coordination/caching.

Redis coordination keys do not replace Deploy/Service state or lifecycle transitions.

## Channels

Channels delivers deployment events and other WebSocket traffic. The deployment state remains authoritative in the database.

## Worker separation

Long-running deployment queues are separated from the dedicated base-image queue. See [deployments/06-workers-concurrency-and-state.md](deployments/06-workers-concurrency-and-state.md).
