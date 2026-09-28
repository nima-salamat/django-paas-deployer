# deployments

## Purpose

deployments is the execution engine: it resolves configuration, compiles plans, builds images, applies runtime resources, proves readiness, rolls back/cleans up and reconciles failures.

## Why this boundary exists

Django domain records should survive workers and HTTP requests without directly owning Docker resources. This package is the side-effect boundary between durable intent/provenance and Docker/Swarm.

## Responsibilities

Planning; platform detection; build/Dockerfile generation; runtime contracts/adapters; state/ownership fencing; readiness; rollback; cleanup; base-image execution policy; DB runtime specialization; reconciliation/recovery.

## Non-responsibilities

Persistent Service desired state is services. Deploy provenance/base-image registry/DeployLog are deploy. Plan policy is plans. User identity is users.

## Documents

- [models.md](models.md) — deliberately no meaningful Django model schema here.
- [../../deployments/README.md](../../deployments/README.md) — canonical deep execution architecture.
- [tests.md](tests.md) — contract tests.

## Main boundary

~~~text
Service/ServiceRevision + Deploy provenance
 -> configuration/planning
 -> build
 -> runtime apply
 -> readiness
 -> activation/state
 -> reconcile/recover
~~~

## Invariants

1. Workers are not sources of desired state.
2. ServiceRevision is immutable execution input.
3. Runtime identity is retained for recovery/cleanup fencing.
4. Desired state, runtime observation and readiness are distinct.
5. Stale workers cannot activate or terminalize newer work.
6. Base-image reuse is fingerprint/lease driven.

## Reading order

Start with ../../deployments/README.md. Then choose 01-system-model through 11-testing-contracts-and-invariants by problem. Read ../services/README.md and ../deploy/README.md for persistence ownership.
