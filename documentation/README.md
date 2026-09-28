# PassDeployer Documentation

This directory is the canonical repository documentation. The Django package at \`src/docs/\` is product code and is intentionally separate.

## Deployment architecture entry point

**For any deployment bug, feature or architectural change, read [documentation/deployments/README.md](deployments/README.md) before opening \`src/deployments/\`.**

The deployments subtree is the living architectural memory of the deployment engine. It records current production paths, migration seams, ownership, contracts, state, concurrency, recovery and test invariants.

## Guides

- [Architecture](architecture.md)
- [Installation](installation.md)
- [Development](development.md)
- [Configuration](configuration.md)
- [Control plane](control-plane.md)

## Deployments

- [Deployments architecture manual](deployments/README.md)
- [System model](deployments/01-system-model.md)
- [Request to plan](deployments/02-request-to-plan.md)
- [Execution lifecycle](deployments/03-execution-lifecycle.md)
- [Build and platforms](deployments/04-build-and-platforms.md)
- [Runtime and Swarm](deployments/05-runtime-and-swarm.md)
- [Workers, concurrency and state](deployments/06-workers-concurrency-and-state.md)
- [Reconciliation and recovery](deployments/07-reconciliation-and-recovery.md)
- [Base images](deployments/08-base-images.md)
- [Logs, health, rollback and cleanup](deployments/09-logs-health-rollback-cleanup.md)
- [Database deployments](deployments/10-database-deployments.md)
- [Testing, contracts and invariants](deployments/11-testing-contracts-and-invariants.md)

## Domain

- [Service domain](domain/services.md)
- [Revisions, environment and secrets](domain/revisions.md)
- [Databases and storage](domain/databases-storage.md)
- [Application catalog](domain/catalog.md)

## Operations

- [Observability](observability.md)
- [Wagtail administration](subsystems/wagtail.md)
- [Testing and security](testing-and-security.md)
- [Project layout](reference/project-layout.md)

## Components

Component documentation outside the deployment architecture manual remains under [components/](components/).

### Documentation maintenance rule

One architectural fact should have one canonical home. Other documents should link to it rather than silently defining a second lifecycle or state model.

When behavior changes, verify the implementation first and update the canonical deployments document that owns the behavior. Historical audit documents are not sources of truth.
