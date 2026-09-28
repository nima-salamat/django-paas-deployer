# deployments contracts

The deployment test suite protects concurrency, planning, runtime and recovery contracts. The complete test file list remains in src/deployments/tests/.

## Contract groups

| Tests | Contract |
|---|---|
| test_deployment_ownership.py | One active execution owner per deployment; replacement workers must not overwrite newer ownership. |
| test_activation_consistency.py | Service.active_revision changes only through the fenced activation path; stale workers cannot activate an older release. |
| test_state_manager_fencing_contract.py | Owner/task-id, cancellation and terminal-state fences are atomic with row locking. |
| test_state_machine.py | Deployment lifecycle transitions remain legal and explicit. |
| test_lifecycle_executor.py | Framework-neutral lifecycle semantics: cancellation, retries, runtime availability/capability and stale cleanup behavior. |
| test_runtime_contract.py | Runtime apply/inspect/wait/stop/rollback semantics and idempotency/identity behavior. |
| test_runtime_characterization.py / test_swarm_runtime.py | Current concrete Swarm runtime behavior and migration characterization. |
| test_base_image_* | Base-image fingerprint, reuse, queueing, cancellation races, lease protection and stale-builder fencing. |
| test_planning_boundaries.py / test_strategy_resolution.py | Plan/strategy boundaries and tenant/operator policy separation. |
| test_build_resource_semantics.py / test_resource_policy.py | Operator resource ceilings and build policy. |
| test_reconciliation_planner.py / test_recovery_operation_journal.py | Fail-closed reconciliation decisions and recovery operation ownership. |
| test_readiness_and_cancellation.py | Backend readiness and cancellation boundary. |
| test_rollback.py | Rollback target semantics and cleanup/activation ordering. |
| test_multiplatform_build.py and platform regressions | Platform detection/build behavior. |
| test_security.py | Tenant-config and runtime security constraints. |

## How to use the suite

A failing contract test should be read as an architectural signal before editing implementation. For example, changing activation code requires reading ownership and activation-consistency tests together; changing a base-image lookup requires reading cache, fingerprint, queue and lease tests together.

Cross-app invariants involving ServiceRevision/activation are also summarized in ../deployments/execution/11-testing-contracts-and-invariants.md.

## Modification rule

A change is not complete when the implementation works in the happy path. Preserve the protected race, cancellation, restart and stale-worker cases represented by these tests.
