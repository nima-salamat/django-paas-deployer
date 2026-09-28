# PassDeployer Documentation

This directory is the canonical repository documentation. The Django package at src/docs/ is product code and is intentionally separate.

## Start here for deployment work

**Before reading implementation under src/deployments/, read [Deployments architecture manual](deployments/README.md).**

The deployments manual is the subsystem's architectural memory. It is ordered by execution responsibility and links to the contracts, state ownership, concurrency rules, runtime behavior, recovery model and tests that should be understood before editing source.

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

Component-level responsibilities outside the deployment architecture manual remain under [components/](components/).

### Documentation maintenance rule

When changing a deployment implementation, update the relevant canonical deployments document only after verifying the behavior against current master code. Historical audit/design notes are not architectural sources of truth.
