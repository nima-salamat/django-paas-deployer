# Observability

## Logs

The `logs` app owns persisted deployment/runtime log data, retention and usage reconciliation.

In Swarm mode the collector discovers managed Swarm Services and consumes `docker service logs`, which is service-level and survives task movement between nodes.

## Runtime state

Service runtime APIs can report desired/running replicas, task states and local CPU/memory when the task exists on the connected Docker Engine.

## WebSockets

Channels publishes realtime events. The durable state remains in PostgreSQL/Docker.

## Shell

Shell resolves the actual Swarm task container. Exec is allowed only if that task is on the connected Docker node.

## Health

Readiness combines Swarm task/service state with configured application healthchecks.
