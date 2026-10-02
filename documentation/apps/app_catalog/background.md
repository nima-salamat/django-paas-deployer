# app_catalog background behavior

start_application_installation claims/continues an ApplicationInstance execution and advances the child-service DAG.

gate_application_service waits for child prerequisites before dispatch. The coordinator never re-resolves the catalog during recovery: its graph comes only from `ApplicationInstance.definition_snapshot._application_orchestration`, while generated credentials remain in ServiceSecret/ServiceSecretVersion.

advance_application_service creates/dispatches the next ApplicationInstanceService child.

application_service_failed records a child failure and prevents unsafe continuation.

cancel_application_installation stops future dispatch and performs safe terminal cleanup.

reconcile_application_installations is the recovery scheduler: it inspects persisted execution_task_id/deadline and child bindings to requeue or fail stale coordinator work. It must not infer a missing child from a transient query result and blindly duplicate it.

Hard deletion is coordinated by `app_catalog.user_deletion.prepare_user_hard_delete`. `ApplicationInstanceService.service` and `ApplicationInstanceService.deploy` remain `PROTECT` for direct child deletion; the user hard-delete coordinator explicitly removes those bindings first, fences each child Service lifecycle generation, deletes the child Service through the normal Service cleanup boundary, and then removes the installation-owned network.

Queue routing for these tasks is configured centrally in src/config/settings.py. Child deployment work remains subject to deployments ownership/retry/fencing rules.

Tests: `tests/test_user_deletion.py`, test_application_plan.py, test_adversarial_contracts.py, test_compatibility.py and integration/test_ready_app_runtime.py protect deletion, planning, security and normal runtime integration.

## Management command: migrate_service_domain

Source: src/app_catalog/management/commands/migrate_service_domain.py.

Backfills legacy catalog child Deploy rows into the Service -> ServiceRevision domain without deleting legacy plaintext data. The optional --application UUID limits the operation to one ApplicationInstance. Rows without a Deploy or with an existing revision are skipped; revision materialization errors are reported and make the command exit non-zero.

This is a migration/repair command, not an installation command. It is safe to rerun for already-revisioned children because those rows are skipped.
