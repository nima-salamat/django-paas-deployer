# deployments

## Purpose

The `deployments` package is the execution engine and infrastructure boundary. It converts immutable service intent into a normalized plan, builds or reuses images, applies runtime resources, proves readiness, activates releases, rolls back failures, cleans owned resources, and reconciles drift.

## Canonical documentation

This directory is the only canonical documentation home for `src/deployments/`. Deep execution contracts live under [execution/](execution/).

## Ownership

| Concern | Owner |
|---|---|
| Desired Service state | `src/services/` |
| Immutable executable revision | `src/services/revisioning.py` |
| Deployment attempt/provenance | `src/deploy/models.py::Deploy` |
| Plan/configuration contracts | `src/deployments/planning/` |
| Lifecycle/worker ownership | `src/deployments/application/` and `src/deployments/celery/` |
| Runtime contracts/adapters | `src/deployments/runtime/` |
| Concrete Docker/Swarm execution | `src/deployments/core/` |
| Reconciliation decisions | `src/deployments/reconciliation/` |

## Execution pipeline

```text
Service
  -> ServiceRevision
  -> Deploy
  -> configuration/provenance
  -> DeploymentPlan
  -> build/platform selection
  -> runtime selection
  -> apply
  -> readiness
  -> activation
  -> cleanup/rollback
  -> reconciliation/recovery
```

## Non-responsibilities

This package does not own tenant desired state, catalog definitions, plan policy, durable secret values, user identity, or a second persistence model for runtime resources.

## Contract documents

- [System model](execution/01-system-model.md)
- [Request to plan](execution/02-request-to-plan.md)
- [Execution lifecycle](execution/03-execution-lifecycle.md)
- [Build and platforms](execution/04-build-and-platforms.md)
- [Runtime and Swarm](execution/05-runtime-and-swarm.md)
- [Workers, concurrency and state](execution/06-workers-concurrency-and-state.md)
- [Reconciliation and recovery](execution/07-reconciliation-and-recovery.md)
- [Base images](execution/08-base-images.md)
- [Logs, health, rollback and cleanup](execution/09-logs-health-rollback-cleanup.md)
- [Database deployments](execution/10-database-deployments.md)
- [Testing, contracts and invariants](execution/11-testing-contracts-and-invariants.md)
- [Models](models.md)
- [Tests](tests.md)

## Source-surface rule

`src/deployments/` contains substantially more architecture than its Django model surface: lifecycle objects, planning contracts, runtime value objects/protocols, platform strategies, Celery tasks, reconciliation decisions, infrastructure adapters and concrete managers. These non-ORM contracts are first-class documentation surfaces and are inventoried by [COVERAGE.md](../COVERAGE.md).

## Migration seams

The current production path still contains deliberate compatibility bridges such as the legacy `Deploy` facade, runtime Swarm adapter, plan-to-legacy configuration compiler, and framework-neutral lifecycle executor. These are documented migration seams, not duplicate ownership models.

## Reading order

Read this README first, then the execution document matching the change. For cross-app ownership, also read [services](../services/README.md) and [deploy](../deploy/README.md).

## Management commands

### consume_docker_events

Source: src/deployments/management/commands/consume_docker_events.py.

Long-running Docker Engine event reconciliation for the non-Swarm container runtime. It consumes managed container lifecycle, health and OOM events and feeds the existing Deploy/DeployLog pipeline. When Swarm is enabled it deliberately does not consume container events and instead remains idle because Swarm task state is reconciled by the scheduler. Docker disconnects are retried with bounded backoff.

### run_log_collector

Source: src/deployments/management/commands/run_log_collector.py.

Runs the persistent runtime-log collector. It discovers managed containers or Swarm services, acquires per-stream leases, catches up recent output, follows live output, enforces logging policy/rate limits, persists sanitized entries when configured, and publishes realtime events. Lease loss stops a follower so a stale collector cannot continue publishing another collector's stream.


## Additional production modules

Recent lifecycle hardening added these first-class production surfaces:

- `src/deployments/common/deadline.py` — shared wall-clock deadline budgeting for blocking operations.
- `src/deployments/common/event_outbox.py` — durable deployment-event projection and retry dispatcher.
- `src/deployments/observability.py` — optional OpenTelemetry/Sentry tracing and secret-safe diagnostics.
- `src/deployments/planning/runtime_spec.py` — immutable runtime/provenance snapshot with secret references rather than secret values.
