# Deployments subsystem

## Purpose

This is the canonical architecture map for the PassDeployer deployment subsystem.

**Read this file before opening implementation files under src/deployments/.** The documents linked here are ordered so a coding model can learn the system boundary, lifecycle, state ownership, runtime contract, failure model, and invariants before making a local source change.

The deployment subsystem turns a service's declarative configuration and a concrete revision into an executable workload on Docker/Swarm. It owns deployment execution and infrastructure interaction; it does not own the user's original service intent.

## Current implementation status

The repository contains an incremental migration toward a runtime-neutral planning/lifecycle architecture.

The important distinction is:

- ServiceRevision is the immutable executable snapshot used by the current application deployment path.
- DeploymentPlan, RuntimeContract, RuntimeRegistry, and DeploymentLifecycleExecutor define a newer architecture seam and are covered by contract tests.
- The current main application path in DeployService._process_deployment() still constructs a transitional execution plan and passes it through DeploymentPlanCompatibilityCompiler into the existing Deploy facade and DeploymentOrchestrator.
- deployments/core/swarm.py is therefore still the concrete Swarm implementation used by the main path. deployments/runtime/swarm/adapter.py is a compatibility adapter around it, not a second independent Swarm implementation.
- Do not remove the bridge or rewrite callers as part of an ordinary bug fix unless the task explicitly concerns that migration.

This manual describes implemented behavior on master and marks transitional contracts explicitly.

## System boundary

~~~text
Service / ServiceProcess / ServiceRevision
        |
        | desired configuration + immutable executable snapshot
        v
Deploy
        |
        | execution ownership, provenance, lifecycle state
        v
deployments/
        |
        | plan/build/runtime/reconciliation
        v
Docker Engine / Docker Swarm
        |
        v
Swarm Service / Swarm Task
~~~

The deployment subsystem owns:

- turning a deployment request into an immutable revision-backed execution input;
- resolving and validating build/runtime configuration;
- platform/framework detection and Dockerfile generation;
- application image production;
- operator-owned base runtime image resolution;
- persistent volume and network preparation;
- runtime application and readiness;
- activation of the winning revision;
- deployment logs/events, cancellation, rollback and cleanup;
- Celery execution, ownership fences and recovery;
- runtime observation and reconciliation.

It does not own:

- the original user-facing service contract;
- plan/resource definition itself;
- ordinary API presentation;
- the business meaning of a Service outside deployment lifecycle;
- unmanaged Docker resources.

## State ownership

| Concept | Primary owner | Meaning |
| --- | --- | --- |
| Service source/build/runtime configuration and desired state | src/services/models.py | Mutable declarative service intent |
| ServiceRevision snapshots | src/services/models.py + src/services/revisioning.py | Immutable executable configuration/provenance |
| Deploy | src/deploy/models.py | One execution attempt, lifecycle/provenance, worker ownership and diagnostics |
| Service/Deploy transitions | src/deployments/common/state_machine.py + src/deployments/core/state/manager.py | Authoritative lifecycle state |
| DeploymentPlan | src/deployments/planning/plan.py | Immutable in-memory normalized execution description |
| ServiceRuntimeGraph | src/deployments/core/runtime_graph.py | Compiled process/endpoints/network/volume/runtime graph |
| Base runtime image registry | src/deploy/models.py + src/deploy/base_images.py | Operator-owned reusable artifacts |
| Runtime observations | src/deployments/runtime/observations.py and concrete runtime code | Observed infrastructure state |
| Service.active_revision | services/revisioning.py / Service | Runtime-authoritative active revision |
| Service.selected_deploy | compatibility projection | Legacy access path; not primary runtime authority |

## End-to-end execution map

~~~text
API / service operation
  -> Deploy row + queued Service
  -> Celery deploy task
  -> DeployService
  -> per-Service advisory lock
  -> Service/Deploy state acquisition
  -> ensure_revision_for_deploy()
  -> materialize revision configuration
  -> normalize/validate configuration
  -> platform + framework resolution
  -> transitional DeploymentPlan -> DeploymentConfig bridge
  -> DeploymentOrchestrator
       -> build context preparation
       -> project inspection / platform enrichment
       -> base-image resolution
       -> Dockerfile rendering
       -> application image build
       -> network/volume preparation
       -> Swarm runtime OR legacy container path when Swarm is disabled
       -> readiness
       -> activation callback
       -> cleanup
  -> terminal Deploy state
  -> legacy Service state compatibility sync
  -> periodic reconciliation / recovery
~~~

Database deployments intentionally diverge at the Celery task boundary and run through DBDeployer; see 10-database-deployments.md.

## Stage ownership map

| Stage | Main implementation | Input | Output/state | Important failure |
| --- | --- | --- | --- | --- |
| Queue | deployments/celery/tasks.py | Deploy id | task execution begins | invalid/cancelled task |
| Ownership | celery/services/deploy_service.py, core/state/locks.py | Service + Deploy | advisory lock + task owner | another owner exists |
| Revision | services/revisioning.py | Deploy.config + Service config | immutable ServiceRevision | snapshot/validation failure |
| Resolution | celery/services/deploy_service.py, common/config.py, planning/configuration.py | revision + policy | effective configuration | forbidden override / invalid input |
| Detection | core/platforms/ + platform_bridge.py | source tree | platform/framework ProjectConfig | no valid detector/config |
| Base image | deploy/base_images.py | runtime identity + definition | reusable image ref + lease | unavailable/mismatched base |
| Plan/bridge | planning/plan.py, planning/bridge.py, core/deploy.py | graph + selection + resolved config | DeploymentConfig for current executor | unsupported capability / bridge mismatch |
| Build | core/dockerfile.py, core/manager/image_manager.py | Dockerfile + source tar | application image | deterministic build or Docker error |
| Runtime | core/orchestrator.py, core/swarm.py | image + runtime config | Swarm services/tasks or legacy container | create/start/update failure |
| Readiness | core/health.py or Swarm readiness | runtime resource | healthy/ready observation | timeout/unhealthy task |
| Activation | DeployService activation callback + services/revisioning.py | ready new revision | active_revision + legacy projection | active revision changed concurrently |
| Recovery | celery/schedules.py | DB + observed runtime | repaired or failed state | ownership/identity cannot be proven |
| Events | core/deployment_logger.py + core/sink.py | stage event | DeployLog + DB progress + WebSocket | sink failure is non-fatal |

## Runtime modes

Swarm is enabled by default in the current configuration. The runtime layer recognizes:

- docker-swarm: normal current runtime backed by Swarm Services/Tasks.
- legacy-docker: compatibility runtime used when SWARM_ENABLED is false.

When Swarm is enabled, the main orchestrator treats Swarm services as runtime state. The legacy Docker-container event consumer is disabled by default and is enabled only through the legacy-runtime Compose profile.

## Base-image rule that matters during debugging

An application deployment does **not** mean “rebuild every base image”.

deploy/base_images.py::ensure_base_images() first derives an operator-owned BaseImageSpec, definition fingerprint and image identity. It checks the local Docker artifact and its fingerprint before deciding to queue a build. A compatible local image may be used even when the registry row is in BUILDING, PENDING, or FAILED renewal state. This separates application deployment execution from operator-managed base-image renewal.

See 08-base-images.md before changing base-image behavior.

## Recommended reading order for coding models

1. This file — system boundary and current-vs-transitional architecture.
2. 01-system-model.md — entities and state ownership.
3. 02-request-to-plan.md — configuration, revision, detection and plan formation.
4. 03-execution-lifecycle.md — real execution order, activation and failure.
5. 04-build-and-platforms.md — source inspection, platforms, Dockerfile and image build.
6. 05-runtime-and-swarm.md — runtime contract and current Swarm implementation.
7. 06-workers-concurrency-and-state.md — Celery, locks, fencing, state transitions and retries.
8. 07-reconciliation-and-recovery.md — desired vs observed state and recovery.
9. 08-base-images.md — separate base-image lifecycle and cache semantics.
10. 09-logs-health-rollback-cleanup.md — diagnostics and cleanup ordering.
11. 10-database-deployments.md — specialized database path.
12. 11-testing-contracts-and-invariants.md — tests and pre-change checklist.
13. Only now inspect the target implementation file.

## Source selection guide

| Problem | Start here | Then inspect |
| --- | --- | --- |
| Deployment state says the wrong thing | core/state/manager.py, common/state_machine.py | deployment_state.py, relevant tests |
| Two deploys race | core/state/locks.py | deploy_service.py, ownership tests |
| Config/platform detection is wrong | planning/configuration.py, core/platforms/registry.py | common/config.py, platform plugin |
| Application image is wrong | core/orchestrator.py, core/dockerfile.py | platform plugin + image manager |
| Base image rebuilds/waits unexpectedly | deploy/base_images.py | base-image models/tasks/tests |
| Runtime/Swarm is wrong | core/swarm.py | runtime/contract.py, adapter, runtime tests |
| Deployment never becomes active | DeployService activation callback | services/revisioning.py, activation tests |
| Worker disappeared | celery/schedules.py + ownership/state manager | recovery tests |
| Logs/events are missing | core/sink.py, core/deployment_logger.py | DeployLog model and observability docs |
| Database deployment is broken | celery/tasks.py::run_db_deploy, core/db_deployer.py | database tests |

## Architectural boundary rules

**Planning owns normalization and policy resolution. It must not call Docker.**

**Runtime owns Docker/Swarm operations. It must not invent tenant configuration policy.**

**The state manager owns authoritative lifecycle transitions. Callers must not bypass it with bare status writes for normal lifecycle changes.**

**A worker that loses execution ownership must stop mutating or cleaning resources that could now belong to a newer execution.**

**Activation happens only after runtime readiness and is fenced against a changed active deployment.**

**Legacy compatibility code may remain at a boundary, but new code should not make it the new architectural source of truth.**

## Related documentation

This subtree is the deployment knowledge base. System-wide architecture is in ../architecture.md. Domain ownership is in ../domain/services.md and ../domain/revisions.md. Runtime logging and observability details are in ../observability.md.
