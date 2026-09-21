# Reconciliation

## Desired versus observed

```text
Service.desired_state
 + Service.active_revision
          |
          v
managed Swarm Services
          |
          v
Swarm Tasks
```

The database is the desired-state store. Docker is the observed runtime authority.

## Periodic repair

Celery Beat repairs state after:

- missed Docker events
- worker crashes
- daemon restarts
- Redis outages
- external Docker changes

## Infrastructure

The Swarm infrastructure sync task imports Docker node identity, role, availability, state, address, resources and labels into `SwarmNode`.

Wagtail changes desired availability/labels; reconciliation applies them back to Docker.

## Event consumer

The legacy container-event consumer is disabled in normal Swarm mode. Swarm service/task ownership is reconciled from the Swarm API instead.

## Logs

In Swarm mode, log collection follows service logs so task movement between nodes does not break the stream.
