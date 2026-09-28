# 11 — Testing, contracts and invariants

## Purpose

Treat tests as executable architecture. Before changing deployment code, read the tests that enforce the relevant boundary.

## Test map

### Planning and configuration

- test_config.py
- test_config_contract.py
- test_deployment_profile.py
- test_planning_boundaries.py
- test_strategy_resolution.py
- test_customization_contract.py

These protect configuration normalization, tenant boundaries, plan/runtime decisions and planning seams.

### Lifecycle, state and ownership

- test_state_machine.py
- test_state_manager_fencing_contract.py
- test_lifecycle_executor.py
- test_integrated_lifecycle_contracts.py
- test_activation_consistency.py
- test_deployment_ownership.py

These are the first tests to read for state, activation or concurrency changes.

### Runtime and Swarm

- test_runtime_contract.py
- test_runtime_characterization.py
- test_swarm_runtime.py
- test_readiness_and_cancellation.py

Use these for runtime semantics, service/task mapping, readiness or cancellation.

### Build and platform

- test_multiplatform_build.py
- test_build_resource_semantics.py
- test_deployer_regressions.py
- test_frontend_build_regressions.py
- test_php_document_root_override.py
- test_container_error_surfacing.py
- test_image_name_validation_static.py
- test_converter.py

### Base images

The base-image cache, fingerprint, queue, lease, retry and cancellation contracts are covered by:

- test_base_image_cache_behavior_v14.py
- test_base_image_cache_fingerprint.py
- test_base_image_cancel_race.py
- test_base_image_integration.py
- test_base_image_policy_contract.py
- test_base_image_queue_and_lease.py
- test_base_image_retry_regressions.py
- test_base_image_runtime_stripping.py
- test_base_images_regressions.py
- test_base_runtime_image_operator_contracts.py

These are the authoritative starting point for unexpected base-image rebuilds or waits.

### Reconciliation and recovery

- test_reconciliation_planner.py
- test_recovery_operation_journal.py
- test_patch_regressions.py
- test_force_cancel_cleanup.py

### Retry, cancellation and failure

- test_retry.py
- test_cancellation_policy.py
- test_readiness_and_cancellation.py
- test_rollback.py
- test_force_cancel_cleanup.py
- test_exceptions.py

### Integration/database

- test_control_plane_migrations.py
- database-related app-catalog/deployment integration tests
- compose.yaml integration profile for deployment integration tests

## Architectural invariants

### 1. State transitions are explicit

Source:

- deployments/common/state_machine.py
- deployments/core/state/manager.py

Invariant:

> Normal Service/Deploy lifecycle mutations go through the authoritative StateManager and legal transition table.

### 2. One deployment owner per Service

Source:

- deployments/core/state/locks.py
- test_deployment_ownership.py

Invariant:

> Two deployment workers cannot safely mutate one Service concurrently.

### 3. Stale workers are fenced

Source:

- StateManager.transition_deploy_if_owned()
- DeployService activation callback
- test_state_manager_fencing_contract.py

Invariant:

> A worker that lost ownership cannot activate, terminalize or clean resources for a deployment it no longer owns.

### 4. Revision is the executable snapshot

Source:

- services/revisioning.py
- test_activation_consistency.py
- planning boundary tests

Invariant:

> After revision materialization, runtime execution should use the immutable revision snapshot rather than mutable Service/Deploy configuration.

### 5. Activation is fenced

Source:

- deployments/celery/services/deploy_service.py
- services/revisioning.py

Invariant:

> A deployment becomes active only after readiness and only while the expected previous deployment is still current.

### 6. Runtime infrastructure is operator-owned

Source:

- deployments/planning/configuration.py
- deployments/runtime/registry.py
- deployments/common/config.py
- test_planning_boundaries.py
- test_security.py

Invariant:

> Tenant configuration cannot select arbitrary host infrastructure or bypass resource/security policy.

### 7. Base-image reuse is fingerprint-aware

Source:

- deploy/base_images.py
- base-image cache/fingerprint tests

Invariant:

> A local base image is reused only when its definition is compatible with the expected operator definition or an explicitly permitted last-known-good fallback.

### 8. Application and base-image lifecycles are separate

Source:

- deploy/base_images.py
- base-image queue/cache tests

Invariant:

> An application deployment must not rebuild a reusable base image merely because its registry row has an active renewal/build state.

### 9. One running Swarm replica per process

Source:

- deployments/core/swarm.py
- services.models.ServiceProcess
- test_swarm_runtime.py

Invariant:

> Current Swarm execution rejects a process replica count other than one.

### 10. Unknown runtime identity fails closed

Source:

- deployments/reconciliation/planner.py
- deployments/runtime/observations.py
- reconciliation tests

Invariant:

> A runtime resource with unknown managed revision identity is not silently adopted as converged.

### 11. Cleanup is ownership-safe

Source:

- deployments/core/cleanup.py
- deployments/core/orchestrator.py

Invariant:

> A deployment does not globally prune or remove Docker resources it cannot prove it owns.

### 12. Observability failure does not invent deployment failure

Source:

- deployments/core/deployment_logger.py
- deployments/core/sink.py

Invariant:

> Failure to persist or broadcast an event must not, by itself, change a successful deployment into a failed one.

## Pre-change checklist

Before modifying deployments, answer:

1. Which persistent state owner does this change affect?
2. Is the change in planning, build, runtime, state, reconciliation, or presentation?
3. Which task/worker owns the operation?
4. Can another worker execute the same operation concurrently?
5. Does the change introduce Docker calls outside the runtime/orchestrator boundary?
6. Does retry classification happen at the correct boundary?
7. Can cancellation race completion?
8. Can a stale worker reach this code?
9. How is the external runtime resource identified as belonging to this Deploy?
10. What diagnostics must survive failure?
11. Does the change alter a state-machine transition?
12. Which existing test proves the invariant?

## Transitional architecture tests

test_lifecycle_executor.py protects the newer framework-neutral lifecycle executor. It does **not** mean that DeploymentLifecycleExecutor is the only production execution path today.

test_runtime_contract.py protects the runtime abstraction while core/swarm.py remains the concrete production implementation behind the adapter seam.

When changing a migration seam, read both contract tests and current-path regression tests.

## Module-to-test guide

| Modification | First tests |
| --- | --- |
| state or transition | test_state_machine.py, test_state_manager_fencing_contract.py |
| service deployment lock | test_deployment_ownership.py |
| activation | test_activation_consistency.py |
| cancellation | test_cancellation_policy.py, test_readiness_and_cancellation.py |
| runtime contract/Swarm | test_runtime_contract.py, test_swarm_runtime.py |
| platform/build | test_multiplatform_build.py, test_deployer_regressions.py |
| base-image cache/build | base-image cache/fingerprint/queue tests |
| reconciliation | test_reconciliation_planner.py, test_recovery_operation_journal.py |
| rollback/cleanup | test_rollback.py, test_force_cancel_cleanup.py |

## Related source map

- lifecycle contracts: src/deployments/application/
- Celery: src/deployments/celery/
- shared policy/safety: src/deployments/common/
- execution/orchestration: src/deployments/core/
- planning: src/deployments/planning/
- reconciliation: src/deployments/reconciliation/
- runtime contracts: src/deployments/runtime/
- Django persistence adapters: src/deployments/infrastructure/
