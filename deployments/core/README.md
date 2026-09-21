# deployments/core

## Responsibility
Docker-neutral deployment execution primitives.

Core components include DeploymentOrchestrator, DeploymentConfig, runtime graph conversion, Docker managers, health checking, rollback and cleanup.

## Boundary
This package must consume normalized service/revision state. It must not query HTTP request objects or treat tenant JSON as an authority for Docker host policy.

## Runtime graph
ServiceRevision -> ServiceRuntimeGraph -> DeploymentConfig -> Docker managers.

## Public API
No HTTP endpoints. This is an internal execution library.
