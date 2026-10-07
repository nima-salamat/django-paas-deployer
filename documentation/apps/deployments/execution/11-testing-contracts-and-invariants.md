# 11 — Testing, contracts and invariants

## Purpose

Tests are the executable memory of deployment architecture.

When changing behavior, find the test that proves the existing contract before deciding that the source is merely an implementation detail.

## Invariant-oriented test map

### Ownership and activation

**`test_deployment_ownership.py`**

Protects:

- one execution owner per Service concept;
- normal PENDING -> RUNNING -> SUCCEEDED flow;
- terminal states are not arbitrarily overwritten;
- replacement of a running service is an explicit allowed state path.

**`test_activation_consistency.py`**

Protects:

- activation happens after readiness;
- replacement resources carry deployment identity;
- stale recovery requires positive ownership;
- stale workers cannot infer success from the old container.

**`test_state_manager_fencing_contract.py`**

Protects:

- task ownership checks;
- cancellation fencing;
- terminal transition ownership.

### State machine

**`test_state_machine.py`**

Protects the legal Service/Deploy transition tables.

Read it before adding a new lifecycle state or transition.

### Lifecycle contract

**`test_lifecycle_executor.py`**

Protects the production lifecycle executor:

- planning -> apply -> readiness -> activate -> success;
- cancellation before side effects;
- retryable runtime failure classification;
- stale worker cannot cleanup;
- cancellation wins completion race;
- runtime unavailable/disabled/unsupported are blocked before activation.

This is a migration contract, not proof that the main DeployService has fully migrated.

**`test_integrated_lifecycle_contracts.py`**

Use for integrated contracts crossing state, lifecycle and runtime abstractions.

## Planning/configuration contracts

**`test_config.py` / `test_config_contract.py`**

Protect parsing and tenant-facing configuration semantics.

**`test_deployment_profile.py`**

Protects profile normalization and backward-compatible aliases.

**`test_planning_boundaries.py`**

Protects configuration precedence, provenance, policy boundaries, plan compilation and the transitional bridge.

**`test_customization_contract.py`**

Protects allowed scoped customizations rather than allowing one override to disable unrelated automation.

**`test_strategy_resolution.py`**

Protects application/database strategy classification.

### Build/platform contracts

**`test_multiplatform_build.py`**

Protects platform-specific build behavior.

**`test_frontend_build_regressions.py`**

Protects Laravel/full-stack frontend build injection and related regression behavior.

**`test_php_document_root_override.py`**

Protects application-level PHP document-root customization from leaking into shared base identity.

**`test_build_resource_semantics.py`**

Protects server-owned build resources.

**`test_deployer_regressions.py`**

Broad deployment regression contracts.

**`test_container_error_surfacing.py`**

Protects propagation of underlying container/Docker diagnostics.

### Runtime/Swarm contracts

**`test_runtime_contract.py`**

Defines runtime-neutral semantics through a fake runtime and the Swarm adapter.

Important examples:

- repeated apply can be idempotent;
- disabled/unreachable/unsupported states remain distinct;
- rollback restores the previous observation;
- Swarm adapter hides Docker SDK-specific types;
- unlabelled external service does not become the desired revision.

**`test_runtime_characterization.py`**

Use to understand current concrete runtime behavior before changing it.

**`test_swarm_runtime.py`**

Protects actual Swarm service/task configuration and lifecycle behavior.

**`test_readiness_and_cancellation.py`**

Protects readiness and mid-deployment cancellation behavior.

### Base-image contracts

**`test_base_image_cache_behavior_v14.py`**

Protects local cache/reuse semantics.

**`test_base_image_cache_fingerprint.py`**

Protects definition-fingerprint compatibility and stable PHP base identity.

**`test_base_image_cancel_race.py`**

Protects build task ownership, cancellation races, queue routing and deployment/base-lease interactions.

**`test_base_image_queue_and_lease.py`**

Protects dedicated queue and lease lifecycle.

**`test_base_image_policy_contract.py`**

Protects operator-owned policy.

**`test_base_image_retry_regressions.py`**

Protects retry behavior and terminal failure handling.

**`test_base_runtime_image_operator_contracts.py`**

Protects operator-visible base lifecycle contracts.

**`test_base_image_runtime_stripping.py`**

Protects the distinction between shared base contents and deployment-specific runtime behavior.

**`test_base_images_regressions.py`**

Broad regression coverage for resolver/build behavior.

### Reconciliation/recovery contracts

**`test_reconciliation_planner.py`**

Protects pure decision semantics:

- missing runtime -> CREATE;
- wrong desired state -> STOP;
- revision drift -> UPDATE;
- unhealthy runtime -> REPAIR;
- unavailable runtime -> BLOCKED;
- unknown identity -> manual intervention.

**`test_recovery_operation_journal.py`**

Use for persistent recovery/operation journal semantics.

**`test_patch_regressions.py`**

Broad safety regressions around patched behavior.

**`test_force_cancel_cleanup.py`**

Protects cancellation cleanup and preservation of existing running state.

### Failure/cancellation/rollback

**`test_retry.py`**

Protects retry classification helpers.

**`test_cancellation_policy.py`**

Protects pure cancellation decisions.

**`test_rollback.py`**

Protects rollback snapshot/restore semantics.

**`test_exceptions.py`**

Protects the unified exception hierarchy and recoverability semantics.

## Contract: RuntimeContract

A compatible runtime implementation should preserve these tested semantics:

1. `apply()` turns a plan into a runtime resource and returns a handle.
2. Repeating an equivalent operation should be safe/idempotent where the backend supports it.
3. `inspect()` reports observed reality, not desired state.
4. `wait_ready()` proves backend readiness; apply success alone is insufficient.
5. `stop()` / `remove()` target the identified resource.
6. `rollback()` needs an explicit known-good target.
7. logs are observational.
8. capability and availability failures remain distinguishable.

## Contract: DeploymentExecutionContext

**Path:** `application/context.py`

It carries:

- deployment/service/revision identity;
- worker task id;
- operation key;
- RuntimeSelection;
- ownership callback;
- cancellation callback;
- event publisher.

### Semantic guarantee

`assert_can_continue()` means:

> this worker still owns the execution and cancellation has not been requested at this safe boundary.

A strategy/runtime implementation should not replace this with an ad-hoc database query.

## Contract: DeploymentStrategy

**Path:** `application/lifecycle.py`, `application/strategies.py`

A strategy owns:

- how a workload-specific plan is built;
- how successful readiness becomes domain activation.

It does not own:

- common lifecycle state machine;
- Celery retry;
- runtime Docker API calls.

## Contract: ConfigurationResolver

Tests and implementation establish:

- bounded layered input;
- deterministic precedence;
- rejected deployment overrides outside the allow-list;
- provenance of effective values;
- policy-ceiling enforcement.

A caller should pass layers rather than reconstruct precedence through hidden conditionals.

## Contract: ReconciliationPlanner

Given the same DesiredRuntimeState + RuntimeObservation + RuntimeSelection, the decision should be deterministic.

It should not mutate infrastructure or database state.

## Contract: StateManager

The semantic contract is:

```text
read current state
 + verify ownership/cancellation
 + validate transition
 + commit state
 = one serialized lifecycle decision
```

A direct status assignment is not equivalent.

## Contract: Base image resolver

The resolver must preserve:

- definition-fingerprint compatibility;
- last-known-good availability where permitted;
- single build ownership per base identity;
- lease-protected cleanup;
- separate base/application timeout phases.

## Pre-change contract checklist

Before modifying deployments:

1. Which invariant am I changing?
2. Which test encodes the current behavior?
3. Is this a migration seam or production path?
4. What object is the input contract?
5. What is the postcondition?
6. What state/ownership fence is required?
7. What happens if cancellation occurs at the boundary?
8. What happens if the worker becomes stale?
9. Which external resource identity proves ownership?
10. Which diagnostic evidence must survive failure?

## Testing by problem

| Problem | First tests |
|---|---|
| state transition | test_state_machine.py + state-manager fencing |
| two deploys race | test_deployment_ownership.py |
| activation race | test_activation_consistency.py |
| cancellation | test_cancellation_policy.py + readiness/cancellation |
| stale worker recovery | activation consistency + recovery journal |
| platform detection/build | multiplatform + deployer regressions |
| Docker/Swarm runtime | runtime contract + Swarm runtime |
| base rebuild/cache | fingerprint + cache + queue/lease tests |
| reconciliation | reconciliation planner |
| rollback | rollback + force-cancel cleanup |
| retry | retry + exceptions |
| config policy/security | config contract + planning boundaries + security |

## Source/test ownership map

| Source change | Read first |
|---|---|
| `celery/tasks.py` | retry + deployment ownership + lifecycle tests |
| `celery/services/deploy_service.py` | activation + ownership + deploy-service regression tests |
| `application/lifecycle.py` | lifecycle executor contract |
| `planning/configuration.py` | planning boundaries |
| `planning/plan.py` | planning boundaries + runtime contract |
| `core/state/manager.py` | state machine + fencing |
| `core/swarm.py` | Swarm runtime + runtime characterization |
| `core/platforms/` | multiplatform build tests |
| `deploy/base_images.py` | base cache/fingerprint/queue/lease tests |
| `reconciliation/planner.py` | reconciliation planner tests |

## What tests do NOT mean

A contract test for a migration seam is not evidence that the seam is already the only production implementation.

Always distinguish:

- pure contract tests;
- current production path regression tests;
- integration tests against Docker/Swarm.

## Related source

- `src/deployments/application/`
- `src/deployments/celery/`
- `src/deployments/common/`
- `src/deployments/core/`
- `src/deployments/planning/`
- `src/deployments/reconciliation/`
- `src/deployments/runtime/`
- `src/deployments/infrastructure/`
