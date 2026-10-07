# Backend application architecture overview

## What this documentation is for

This page is the high-level map of the Django backend. It explains the main flow and the ownership boundaries without replacing the deeper per-app contracts.

Source code is authoritative. When this overview conflicts with a detailed contract or the implementation, inspect the detailed contract and tests before changing behavior.

## The core idea

Paas Deploy(er) separates **what the customer wants** from **how the platform executes it**.

```text
HTTP / Agent / Ready App request
        |
        v
domain state (Service / ApplicationInstance)
        |
        v
immutable executable snapshot (ServiceRevision)
        |
        v
Deploy record + execution owner
        |
        v
configuration + deployment plan
        |
        v
runtime adapter / Docker Swarm
        |
        v
readiness proof
        |
        v
activation
        |
        +--> deployment events
        +--> runtime logs
        |
        v
reconciliation / recovery when external state drifts
```

The important rule is that activation is the commit point: a built image or a running container/task is not enough to make a release authoritative.

## Main application boundaries

| App/package | Owns | Does not own |
|---|---|---|
| `users` | identity, profiles, roles and ownership | authentication protocol |
| `auth_users` | sessions, OTP/recovery and authentication | workload state |
| `services` | desired workload state, processes, secrets, volumes, networks, sharing and revisions | Docker/Swarm execution |
| `plans` | tenant resource/pricing policy | deployment orchestration |
| `deploy` | Deploy provenance, deployment logs and base-image registry metadata | runtime execution |
| `deployments` | planning, lifecycle, runtime execution, rollback and reconciliation | tenant desired state |
| `app_catalog` | curated definitions and multi-service installation coordination | the child service runtime |
| `logs` | persistent runtime service-log ingestion/query | deployment state |
| `agent` | machine control-plane authentication, scopes, contracts and audit | a second runtime engine |

The full application map is in [README.md](README.md).

## Service and revision authority

A Service has durable desired state. Changes to executable configuration are materialized into an immutable `ServiceRevision`.

```text
Service.desired_state
        |
        v
ServiceRevision
        |
        v
Deploy
        |
        v
deployments
```

`Service.active_revision` is the current runtime-authoritative release pointer.

`Service.selected_deploy` is a compatibility projection. Runtime code must not use it as an independent source of truth. A controlled migration bridge may backfill an active revision for older data, but new activation flows commit the revision first.

## Deployment lifecycle

The normal Swarm production execution path is native: `Celery -> DeployService -> DeploymentLifecycleExecutor -> RuntimeContract -> SwarmRuntimeAdapter -> SwarmRuntime`. Legacy orchestrator components remain isolated for explicit non-Swarm compatibility.

At a high level:

1. A Deploy is claimed by one worker.
2. The worker creates or loads the immutable revision snapshot.
3. The deployment compiles configuration into a normalized plan.
4. Platform/base-image/application-image decisions are made.
5. Docker/Swarm resources are applied.
6. Runtime readiness is checked.
7. Activation re-locks the Service and verifies worker/deployment ownership.
8. The successful revision becomes authoritative.
9. Old resources are cleaned only after the new release is committed.
10. Reconciliation handles crashes or external drift without assuming that a same-name resource belongs to a stale worker.

`DeploymentLifecycleExecutor` and `RuntimeContract` are now the production Swarm lifecycle contracts. The concrete `DeploymentOrchestrator` path is retained only for explicit non-Swarm compatibility and is documented as such under [deployments/execution/03-execution-lifecycle.md](deployments/execution/03-execution-lifecycle.md).

## Cancellation and concurrency

Cancellation is an intent, not merely an HTTP response.

For queued work:

```text
PENDING -> CANCELLED
```

For active work:

```text
cancel_requested
       |
       v
worker observes a safe boundary
       |
       v
owned runtime cleanup
       |
       v
CANCELLED
```

Deployment ownership uses database state plus worker identity and lifecycle fencing. A stale worker must not overwrite newer service intent or delete a resource it no longer proves it owns.

## Ready Apps

`app_catalog` resolves a curated definition into an application plan. Installation creates an `ApplicationInstance`, then ordinary child `Service` and `Deploy` rows.

```text
catalog definition
   -> validation / resolution
   -> ApplicationInstance
   -> child Services + Deploys
   -> normal deployment lifecycle
   -> installation coordinator status
```

The coordinator owns dependency ordering, dispatch/recovery and application-level status. It does not implement a second container runtime.

Secrets remain in the existing Service secret/version system. Public Ready Apps expose configuration slots and safe metadata, not secret plaintext.

## Agent API

The Agent app exposes a versioned control-plane API at `/agent/v1/`.

Agent authorization is:

```text
Agent scope
  AND
existing PassDeployer user authorization
  AND
ServiceShare permission when applicable
```

The Agent API delegates service/deployment/shell operations to existing domain boundaries. Its discovery surfaces are `/capabilities`, `/openapi.json` and `/agent.md`.

## Logs and events

There are two distinct operational data paths:

- **Deployment lifecycle events:** durable `DeployLog` / event-outbox records.
- **Runtime service logs:** `ServiceLogStream` / `ServiceLogEntry` records populated by the runtime log collector.

They answer different questions and must not be merged into one source of truth.

## Reconciliation

The database is authoritative for durable tenant intent; Docker/Swarm is authoritative for observed runtime state.

Reconciliation compares the two and converges them using ownership evidence, lifecycle fences and idempotent operations.

A stale or crashed worker is not allowed to infer success merely because a resource with a familiar name is running.

## Where to read next

- [Application map](README.md) — all first-party Django apps and cross-app boundaries.
- [Services](services/README.md) — desired state, revisions, shares and service APIs.
- [Deployments](deployments/README.md) — execution engine and runtime contracts.
- [Ready Apps](app_catalog/ready-apps.md) — public catalog behavior and installation contract.
- [Agent](agent/README.md) — machine control-plane contract.
