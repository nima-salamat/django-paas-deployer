# deployments

## Responsibility
Internal execution subsystem: Celery tasks, Docker image builds, container lifecycle, networking, volumes, health checks, rollback, cleanup, reconciliation, platform detection, resource policies and runtime graph execution.

It does not own user-facing Service configuration.

## HTTP API
No public REST endpoints are implemented by this package.

## WebSocket
WS /ws/deployments/<uuid:deploy_id>/
Streams deployment events to authorized subscribers.

## Internal architecture
deployments.celery owns asynchronous operations.
deployments.core.orchestrator owns the Docker lifecycle pipeline.
deployments.core.runtime_graph is the Docker-neutral runtime boundary.
deployments.core.platforms owns framework/platform detection plugins.
deployments.core.state owns state transitions, ownership and locks.

## Security boundary
Tenant JSON cannot pass privileged/device/host-network-style Docker host configuration directly into Docker host config.
