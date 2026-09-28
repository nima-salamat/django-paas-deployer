# app_catalog background behavior

start_application_installation claims/continues an ApplicationInstance execution and advances the child-service sequence.

gate_application_service waits for child prerequisites before dispatch.

advance_application_service creates/dispatches the next ApplicationInstanceService child.

application_service_failed records a child failure and prevents unsafe continuation.

cancel_application_installation stops future dispatch and performs safe terminal cleanup.

reconcile_application_installations is the recovery scheduler: it inspects persisted execution_task_id/deadline and child bindings to requeue or fail stale coordinator work. It must not infer a missing child from a transient query result and blindly duplicate it.

Queue routing for these tasks is configured centrally in src/config/settings.py. Child deployment work remains subject to deployments ownership/retry/fencing rules.

Tests: test_application_plan.py, test_adversarial_contracts.py, test_compatibility.py and integration/test_ready_app_runtime.py protect planning, security and normal runtime integration.
