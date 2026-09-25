# deployments

Internal execution subsystem.

Owns Celery tasks, image builds, runtime graph execution, Swarm runtime, health/readiness, rollback, cleanup, reconciliation, log/event collection and platform detection.

It has no public REST router of its own; deployment WebSockets are exposed under `/ws/deployments/<deploy_id>/`.
