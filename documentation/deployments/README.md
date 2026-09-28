# Deployments architecture manual

## Read this first

**This file is the canonical entry point for deployment architecture. Read it before opening source under \`src/deployments/\`.**

The purpose is not to list modules. It is to preserve the reasoning needed to modify the deployment engine safely.

When this manual and implementation disagree, **current master code is authoritative**. Update the manual rather than rationalizing a stale claim.

## What the subsystem does

PassDeployer turns durable Service intent plus an immutable ServiceRevision into runtime infrastructure and then continuously reconciles that infrastructure.

~~~text
Service / ServiceProcess
        |
        | mutable desired intent
        v
ServiceRevision
        |
        | immutable executable snapshot
        v
Deploy
        |
        | one execution + ownership + provenance
        v
deployments application/planning/build/runtime
        |
        v
Docker Engine / Swarm
        |
        v
Swarm Service / Task
~~~

The deployment subsystem owns execution, not the business definition of the Service.

### Ownership map

| Concern | Owner | Why |
|---|---|---|
| User/service intent | \`src/services/\` | It must remain durable and declarative. |
| Immutable executable intent | \`services.revisioning\` | Deployment must not race mutable Service fields. |
| One execution attempt | \`src/deploy/models.py::Deploy\` | Provenance, timing, ownership and diagnostics belong to the attempt. |
| Normalized execution description | \`deployments/planning/\` | Planning needs a runtime-neutral contract before infrastructure calls. |
| Docker/Swarm calls | \`deployments/core/\` + runtime adapters | Infrastructure state is external and must be isolated from policy. |
| Persisted lifecycle transitions | \`deployments/core/state/\` + \`common/state_machine.py\` | State changes need one auditable transition contract. |
| Desired/observed repair choice | \`deployments/reconciliation/\` and current monitor | Reconciliation must not silently redefine desired state. |
| Async execution | \`deployments/celery/\` | Long-running work, retries and worker ownership belong at the async boundary. |

## Current architecture versus migration seams

There is an intentional incomplete migration.

### Current production application path

\`\`\`text
Celery deploy task
  -> DeployService.execute()
  -> advisory lock
  -> StateManager.lock_and_get_deployment()
  -> ensure_revision_for_deploy()
  -> _process_deployment()
  -> ServiceRuntimeGraph.from_revision()
  -> _compile_compatibility_plan()
       -> ConfigurationResolver
       -> DjangoRuntimeSelectionResolver
       -> DeploymentPlanCompiler
  -> Deploy facade
  -> DeploymentOrchestrator
  -> SwarmRuntime (when enabled)
\`\`\`

This means the newer planning/runtime/application contracts are **already real**, but they are not yet the only path.

### Migration seams

- \`DeploymentPlanCompatibilityCompiler\` translates a plan back into the legacy \`DeploymentConfig\`.
- \`core/deploy.py::Deploy\` remains a compatibility facade around \`DeploymentOrchestrator\`.
- \`runtime/swarm/adapter.py::SwarmRuntimeAdapter\` wraps \`core/swarm.py::SwarmRuntime\`.
- \`application/lifecycle.py::DeploymentLifecycleExecutor\` is the framework-neutral lifecycle seam; the main \`DeployService\` path has not yet replaced the concrete orchestrator with it.
- \`reconciliation/planner.py::ReconciliationPlanner\` is a pure decision model; the scheduled monitor still contains concrete Docker/Swarm repair logic.

Do not “finish” these migrations accidentally while fixing an unrelated bug.

## Dependency direction

The intended semantic direction is:

~~~text
Service domain / revision
        |
        v
Application deployment boundary
        |
        v
Planning / strategy
        |
        v
Runtime contract
        |
        v
Concrete runtime
        |
        v
Docker / Swarm
~~~

Two compatibility exceptions are deliberate:

1. the application boundary still calls the legacy \`Deploy\` facade, which uses the orchestrator;
2. the runtime adapter currently delegates down into \`core/swarm.py\`.

There is a second direction for reconciliation:

~~~text
Desired state + revision provenance
              |
              v
Runtime observation
              |
              v
Reconciliation decision
              |
              v
Runtime action
~~~

And the async direction:

~~~text
Celery task
   -> ownership/state gate
   -> lifecycle/execution
   -> external runtime
   -> terminal state
~~~

### Boundary rule

A dependency is not justified merely because a symbol is importable.

If you are tempted to make a Docker call from planning, put lifecycle transitions in a platform plugin, or let reconciliation invent configuration, stop and identify the owner first.


## How to use the major packages

### \`application/\`

Use this package when changing the **semantic lifecycle contract**.

- \`DeploymentExecutionContext\` carries immutable identity, worker ownership, cancellation and event ports.
- \`DeploymentLifecycleExecutor\` owns the generic sequence of plan -> apply -> readiness -> activation -> terminal state.
- \`DeploymentStrategyResolver\` chooses the workload strategy.
- \`cancellation.py\` contains framework-neutral cancellation policy.

**Called by:** the current system still composes most production execution through \`DeployService\`; the framework-neutral executor is the migration/contract seam.

**Preconditions:** lifecycle composition must already have a RuntimeSelection, strategy, persistence port and ownership/cancellation callbacks.

**Must not:** perform Django ORM work or Docker SDK calls in the framework-neutral application layer.

### \`celery/\`

Use this package when changing **asynchronous ownership**: queue selection, retry policy, scheduled monitor work, stop/redeploy task boundaries or task-id fencing.

**Called by:** API/service operations, Beat and recovery paths.

**Consumes:** durable IDs plus a Celery task id.

**Produces:** asynchronous invocation of the lower lifecycle/runtime layers.

**Must not:** duplicate the deployment state machine or make queue delivery itself authoritative runtime state.

### \`common/\`

Use common modules for rules that must be shared across multiple deployment paths:

| Module | Use |
|---|---|
| \`config.py\` | Parse/sanitize Deploy.config and enforce the public config vocabulary |
| \`deployment_profile.py\` | Normalize legacy flat/nested build/runtime profiles |
| \`resource_policy.py\` | Resolve server-owned build/runtime resources |
| \`security.py\` | Validate commands, names and host-path boundaries |
| \`retry.py\` | Shared bounded retry classification |
| \`exceptions.py\` | Error categories and recoverability |
| \`state_machine.py\` | Legal Service/Deploy transitions |

A new rule belongs here only when it is genuinely cross-cutting. Do not move Docker behavior here for convenience.

### \`core/\`

Use this package when fixing the **current concrete execution implementation**.

Start at:

- \`orchestrator.py\` for the end-to-end concrete pipeline;
- \`swarm.py\` for actual Swarm API behavior;
- \`manager/\` for Docker client/image/network/volume/container operations;
- \`platforms/\` for source/framework interpretation;
- \`state/\` for locking and lifecycle persistence;
- \`health.py\`, \`rollback.py\`, \`cleanup.py\` for safety-sensitive execution stages.

This package contains migration-era concrete behavior. Before extracting or moving a component, inspect its current caller in \`DeployService\`.

### \`planning/\`

Use this package for deterministic conversion of resolved facts into a normalized execution description.

**Precondition:** values should already be represented as bounded configuration/runtime inputs.

**Output:** \`ResolvedConfiguration\`, provenance and \`DeploymentPlan\`.

**Must not:** call Docker or mutate lifecycle state.

### \`reconciliation/\`

Use this package when the question is:

> “Given desired state and observed runtime state, what action should be chosen?”

The planner should return a decision. A runtime executor should perform the actual Docker operation.

### \`runtime/\`

Use this package when changing backend-neutral runtime semantics: identity, capabilities, availability, handles, observations or backend selection.

Use \`runtime/swarm/adapter.py\` for the migration seam. Use \`core/swarm.py\` for the current concrete Swarm implementation.

### \`infrastructure/\`

Use these adapters when framework-neutral application contracts need Django persistence/runtime composition.

- \`django_lifecycle.py\` -> LifecycleStore backed by StateManager.
- \`django_runtime.py\` -> Django loading of operator-managed cluster context and RuntimeRegistry selection.
- \`django_cancellation.py\` -> cancellation policy applied under the authoritative Deploy row lock.

**Must not:** become a second home for domain policy. Adapters translate between ports and Django state.

### Package interaction rule

When debugging, move **down one architectural layer at a time**:

~~~text
domain intent
  -> revision
  -> application/lifecycle or DeployService
  -> planning
  -> platform/build
  -> runtime
  -> Docker/Swarm
~~~

Move back upward only when the lower layer reports a state/concurrency/ownership problem.

Do not skip directly from an API symptom to Docker code without first locating the layer that owns the decision.

## Module map

| Area | Architectural responsibility | Entered from | Produces | Must not own |
|---|---|---|---|---|
| \`application/\` | framework-neutral lifecycle sequencing, cancellation, strategy ports | future/current lifecycle composition | lifecycle result | Docker details or Django queries |
| \`celery/\` | task routing, worker boundaries, concrete Django execution | API/monitor/beat | async work + task ownership | business rules that belong to planning/state |
| \`common/\` | shared parsing, safety, policy, retries, state machine | all layers | normalized inputs/errors/rules | Docker execution |
| \`planning/\` | configuration resolution, provenance, DeploymentPlan | DeployService / strategy | immutable plan | Docker calls |
| \`core/platforms/\` | source inspection and framework detection | orchestrator/platform bridge | DetectionResult + ProjectConfig | lifecycle state and Docker |
| \`core/\` | concrete legacy-compatible orchestration, Docker managers, Swarm runtime | Deploy facade/monitor | runtime side effects | tenant policy decisions |
| \`core/state/\` | advisory locks + persisted state transitions | Celery/services/monitor | ownership and state commits | long-running Docker work under row locks |
| \`infrastructure/\` | Django adapters for ports/contracts | application contracts | persisted state/runtime selection | framework-neutral policy |
| \`reconciliation/\` | pure desired-vs-observed decision model | monitor/future executor | safe action decision | direct Docker calls |
| \`runtime/\` | runtime backend contract/selection/observation | application/reconciliation | runtime-neutral handle/observation | tenant policy |
| \`runtime/swarm/\` | contract adapter around current Swarm implementation | runtime registry | RuntimeOperationResult | second independent Swarm engine |

## End-to-end deployment call chain

The arrows below are semantic contracts, not decoration.

| Transition | Caller | Input | Important effect | Consumer |
|---|---|---|---|---|
| request -> Deploy | service/API layer | requested service state/config | creates PENDING Deploy and queues async work | Celery |
| Celery -> DeployService | \`deploy()\` | deploy id + Celery task id | establishes async owner | DeployService |
| DeployService -> lock | \`execute()\` | Service id | serializes all same-Service deployment/stop work | _execute_locked |
| lock -> state start | \`StateManager.lock_and_get_deployment()\` | Deploy id + task id | Service QUEUED→DEPLOYING; Deploy PENDING→RUNNING | lifecycle |
| state -> revision | \`ensure_revision_for_deploy()\` | Deploy + Service | freezes executable snapshot | materializer |
| revision -> graph | \`ServiceRuntimeGraph.from_revision()\` | immutable revision | reconstructs process/runtime semantics | planning/orchestrator |
| graph -> plan | \`DeploymentPlanCompiler.compile()\` | graph + selection + resolved config | validates capabilities and freezes execution description | compatibility bridge |
| plan -> legacy DTO | \`DeploymentPlanCompatibilityCompiler.compile()\` | plan + base config | maps plan into current orchestrator DTO | Deploy facade |
| DTO -> orchestration | \`DeploymentOrchestrator.deploy()\` | DeploymentConfig | validates, builds image, applies runtime | Swarm/legacy runtime |
| runtime -> readiness | concrete runtime/health checker | runtime resource | proves resource can serve | activation |
| readiness -> activation | DeployService callback | revision id + previous-deploy expectation | commits active revision under Service lock | Service |
| activation -> cleanup | orchestrator | active replacement + previous resources | removes old owned resources | terminal state |
| cleanup -> terminal | \`DjangoDeploymentState.finish()\` | result + owner | owned terminal state commit | reconciliation |

## Important lifecycle distinction

Do not confuse:

- **desired state**: what the Service says should run;
- **revision**: immutable executable snapshot;
- **Deploy**: one attempt to make a revision active;
- **runtime observation**: what Docker/Swarm currently reports;
- **worker ownership**: which task may still mutate the attempt;
- **terminal state**: what the database records after lifecycle completion.

A system can be:

- desired running but runtime missing;
- runtime running but desired stopped;
- runtime healthy but not the currently active revision;
- Deploy succeeded but Service state still being reconciled;
- worker stale while a runtime resource exists.

Those are different states and must not be collapsed.

## Architectural rationale

### Why revisioning exists

Service fields are mutable while a build/deploy may take minutes.

Freezing a revision prevents:

- a later Service edit from changing an in-flight deployment's effective configuration;
- rollback from depending on mutable current settings;
- old Deploy rows from being the only reproducibility source;
- activation from mixing one deployment's runtime with another deployment's configuration.

### Why planning exists

Planning separates “what should be executed” from “how Docker happens to represent it”.

That boundary permits:

- capability checks before runtime calls;
- provenance of effective values;
- deterministic contract tests;
- multiple runtime backends without duplicating tenant policy logic.

### Why runtime is separate

Runtime is the infrastructure side of the contract. It should receive resolved intent and translate it into infrastructure.

If runtime starts deciding tenant configuration, Docker API details become a hidden second configuration system.

### Why reconciliation is separate

Reconciliation sees that reality differs from desired state and chooses a repair action. It should not silently change desired state to match whatever happens to be running.

### Why state management is separate

Deployment state changes happen at concurrency boundaries. A state write is therefore more than assigning a string: it must validate the previous state, ownership and cancellation conditions.

## Reading order

1. This README.
2. [01-system-model.md](01-system-model.md) — nouns and ownership.
3. [02-request-to-plan.md](02-request-to-plan.md) — how inputs become a plan.
4. [03-execution-lifecycle.md](03-execution-lifecycle.md) — actual production call path.
5. [04-build-and-platforms.md](04-build-and-platforms.md) — source/build semantics.
6. [05-runtime-and-swarm.md](05-runtime-and-swarm.md) — runtime contract and concrete Swarm.
7. [06-workers-concurrency-and-state.md](06-workers-concurrency-and-state.md) — locks, state, queues, races.
8. [07-reconciliation-and-recovery.md](07-reconciliation-and-recovery.md) — drift and crash recovery.
9. [08-base-images.md](08-base-images.md) — shared runtime image lifecycle.
10. [09-logs-health-rollback-cleanup.md](09-logs-health-rollback-cleanup.md) — diagnostics and destructive boundaries.
11. [10-database-deployments.md](10-database-deployments.md) — specialized branch.
12. [11-testing-contracts-and-invariants.md](11-testing-contracts-and-invariants.md) — executable architecture.
13. Only then open the specific source module.

## Problem-oriented navigation

| Problem | Start here | Then inspect | Why | Primary invariant/test |
|---|---|---|---|---|
| Base image unexpectedly rebuilds | 08-base-images.md | \`deploy/base_images.py\` | resolver owns compatibility/cache decision | fingerprint/cache tests |
| Deployment stuck RUNNING | 03 + 06 | \`deploy_service.py\`, monitor | RUNNING is DB state, not proof of runtime health | ownership/state/recovery tests |
| FAILED while runtime is healthy | 03 + 09 | state tracker + event sink + runtime labels | terminal DB state and runtime observation can diverge | activation/reconciliation tests |
| Deployment never activates | 03 | DeployService activation callback + revisioning | activation is fenced and happens after readiness | test_activation_consistency.py |
| Two deployments race | 06 | locks + DeployService | advisory lock spans external work | test_deployment_ownership.py |
| Cancellation races completion | 06 + 03 | cancellation gateway + state manager | cancellation is serialized under the owner fence | test_lifecycle_executor.py |
| Worker disappears | 07 + 06 | monitor + state manager | recovery must prove ownership | recovery/ownership tests |
| Swarm exists but not ready | 05 + 09 | \`core/swarm.py\`, health | runtime readiness differs from app readiness | test_swarm_runtime.py |
| Wrong framework/platform | 04 + 02 | platform registry/plugin + _process_deployment | detection and policy refinement are separate | multiplatform tests |
| Wrong Dockerfile | 04 | platform bridge + DockerfileGenerator | build inputs were wrong before Docker ran | build regressions |
| Image builds, runtime fails | 05 + 09 | SwarmRuntime/orchestrator | build success does not imply runtime readiness | runtime/readiness tests |
| Persistent volume disappears | 09 + domain storage docs | volume manager + runtime placement | persistence is registered/owned separately | storage/deployment regressions |
| Reconciliation removes wrong resource | 07 | monitor identity checks | same-name is not proof of ownership | recovery tests |
| Docker logs exist but UI does not | 09 | DeploymentLogger + DBAndChannelEventSink | delivery is best-effort and separate from runtime outcome | sink/event tests |
| Database deployment differs | 10 | run_db_deploy + DBDeployer | database path specializes init/readiness | database integration/regression tests |
| Retry occurs unexpectedly | 06 | tasks + common exceptions/retry | retryability is an explicit error property | test_retry.py |
| Retry does not occur | 06 + exceptions | task boundary + error classification | non-recoverable means no automatic retry | retry/failure tests |

## Safe modification rule

Before modifying any deployment component, answer:

1. What architectural owner should own the behavior?
2. Is this desired state, immutable intent, execution state, observed state or worker ownership?
3. What is the caller's precondition?
4. What is the callee's postcondition?
5. Which worker owns the external side effect?
6. What happens if cancellation or ownership loss occurs at that exact line?
7. Which existing test proves the invariant?
8. What must not be bypassed?



## Ready-to-Deploy integration boundary

`app_catalog` supplies installation intent and materialized Services/Deploys; it does not execute them. Catalog DB children use the normal `Deploy` path and are routed by `deployments.celery.tasks.run_db_deploy` to `DBDeployer`. Application-level DAG state is owned by `ApplicationInstance`; child execution state remains owned by `Deploy`.
