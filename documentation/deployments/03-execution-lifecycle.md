# 03 — Execution lifecycle

## Purpose

Document the real execution order and the boundaries at which state, ownership, readiness and activation change.

## High-level sequence

~~~text
queued
  -> ownership acquired
  -> Service DEPLOYING / Deploy RUNNING
  -> revision secured
  -> config/platform resolved
  -> base image ready
  -> application image built
  -> networks/volumes prepared
  -> runtime applied
  -> readiness proven
  -> active revision committed
  -> cleanup
  -> Deploy SUCCEEDED
~~~

Failure or cancellation can exit this path before activation.

## 1. Celery entry

deployments.celery.tasks.deploy is the application task.

It rejects or redirects database platforms to run_db_deploy, suppresses execution when cancellation is already terminal, calls DeployService.execute(deploy_id, task_id=request.id), retries only explicitly recoverable DeploymentError instances, and treats unknown Python exceptions as non-recoverable platform failures.

The task itself does not contain the full deployment algorithm.

## 2. Per-Service ownership

DeployService.execute() acquires acquire_service_deployment_lock(service_id) before changing deployment state or touching Docker.

The lock is a PostgreSQL advisory lock held across the full Celery task.

Row locks alone are too short-lived for image builds and other multi-stage Docker operations.

## 3. State acquisition

StateManager.lock_and_get_deployment() atomically locks the Deploy and Service rows.

It verifies task ownership and that the Service is QUEUED, then transitions:

~~~text
Service: QUEUED -> DEPLOYING
Deploy:  PENDING -> RUNNING
~~~

It stores task ownership and heartbeat data.

A task that cannot satisfy these preconditions is skipped rather than creating a parallel execution.

## 4. Revision boundary

ensure_revision_for_deploy() guarantees an immutable ServiceRevision exists.

The deployment then materializes revision configuration and normalizes it. Mutable Deploy.config is only the compatibility input used when the revision is first created.

## 5. Phase budgets

The deployment has separate lifecycle clocks:

~~~text
base-image phase
    -> base_image_wait_started_at
    -> base_image_ready_at
    ->
application phase
    -> application_started_at
~~~

The base-image wait budget is separate from the application deployment budget.

## 6. Orchestrator stages

DeploymentOrchestrator.deploy() currently performs:

1. initial cancellation check;
2. config validation;
3. ZIP-to-tar build-context conversion;
4. project extraction and platform auto-detection/enrichment;
5. base runtime image resolution;
6. application-phase clock start;
7. Dockerfile rendering;
8. previous container snapshot when the legacy runtime is enabled;
9. application image build;
10. Docker network and managed volume preparation;
11. runtime application:
   - Swarm Services/Tasks when Swarm is enabled;
   - legacy container replacement when Swarm is disabled;
12. readiness;
13. activation callback;
14. cleanup and completion logging.

Progress numbers are diagnostic only; lifecycle state must not be inferred from a progress percentage.

## 7. Swarm activation boundary

In Swarm mode, SwarmRuntime.apply_processes() creates or updates the requested process services.

Readiness requires the current runtime invariant of one running task for each enabled process.

Only after readiness does the orchestrator call the activation callback supplied by DeployService.

The activation callback:

1. locks the Service in a transaction;
2. reads the currently active Deploy;
3. verifies it is still the expected previous deployment;
4. calls activate_revision_locked();
5. sets desired state to running.

If the active deployment changed while this execution was building, activation fails closed.

## 8. Legacy runtime path

When SWARM_ENABLED=false, the orchestrator may use the compatibility container runtime.

The replacement strategy is:

~~~text
existing container
   -> rename old
   -> create replacement
   -> start replacement
   -> health check
   -> activate
   -> remove old
~~~

This keeps the old resource available during create/start and gives rollback a stable restoration target.

The legacy path is not the normal Swarm architecture.

## 9. Cancellation

Cancellation is a two-level mechanism.

Before execution, DjangoDeploymentCancellationGateway can terminalize a PENDING deployment immediately.

During execution, RUNNING or ROLLING_BACK first receives cancel_requested, the worker checks cancellation between stages, the orchestrator raises DeploymentCancelled, runtime cleanup is performed only while the worker still owns execution, and the Deploy state is committed as CANCELLED.

## 10. Failure

The unified exception hierarchy distinguishes validation, Docker/build/runtime, rollback, cleanup, lock/ownership, cancellation, base-image and internal platform failures.

The orchestrator converts ordinary exceptions into DeploymentError subclasses at its boundary.

The Celery task uses recoverable rather than retrying every deployment error.

A deterministic Dockerfile/build problem should not be retried merely because it happened inside a worker.

## 11. Rollback

When a legacy container replacement has a captured snapshot, failures after mutation can restore the previous resource.

The newer lifecycle executor can also use a plan-level rollback_plan through the runtime contract.

Current main application execution still performs concrete rollback through DeploymentOrchestrator/rollback manager and legacy container snapshot logic. Do not describe plan-level rollback as the only live path.

Rollback failure is surfaced through rollback_failed; it is not silently treated as success.

## 12. Cleanup ordering

Application deployment cleanup is intentionally after the activation boundary.

Before activation, cleanup must never destroy the only known-good release.

After activation old legacy containers and obsolete process containers can be removed. Global Docker garbage collection is not performed by the deployment.

CleanupManager.prune_dangling_images() explicitly refuses host-wide pruning.

Base-image leases are released in the orchestrator finally block.

## State transition summary

~~~text
Deploy:
PENDING
  -> RUNNING
      -> SUCCEEDED
      -> FAILED
      -> CANCELLED
      -> ROLLING_BACK
          -> ROLLED_BACK
          -> FAILED

Explicit operator re-execution may move terminal Deploy -> PENDING.
~~~

The exact legal transition table lives in deployments/common/state_machine.py. Do not introduce a new transition by writing the field directly.

## Interruption model

If a worker disappears, reconciliation checks the DB lifecycle and external resource identity. It must prove that a resource belongs to the stale deployment before removing or restoring it. It must not infer successful activation from an unrelated existing resource.

## Related code

- src/deployments/celery/tasks.py
- src/deployments/celery/services/deploy_service.py
- src/deployments/core/orchestrator.py
- src/deployments/core/state/manager.py
- src/deployments/common/state_machine.py
- src/deployments/application/lifecycle.py
