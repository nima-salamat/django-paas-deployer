
# Deployment architecture conformance

This document is source-backed and records the effective deployment control-plane
contracts after the native Swarm lifecycle cutover.

## Authoritative objects

| Concern | Authoritative object |
|---|---|
| Mutable service intent | services.Service |
| Immutable executable intent | services.ServiceRevision |
| Promotable immutable unit | deploy.Release |
| Immutable build identity | deploy.BuildArtifact |
| One execution attempt | deploy.Deploy |
| External resource ownership | deploy.DeploymentResource |
| Durable lifecycle events | deploy.DeploymentEventOutbox |
| Runtime contract | deployments.runtime.RuntimeContract |
| Runtime implementation | deployments.runtime.swarm.SwarmRuntimeAdapter -> core.swarm.SwarmRuntime |

Service.active_revision remains the executable authority. Release and Deploy
records provide provenance and lifecycle state; they do not create a second
current-version pointer.

## Production execution path

~~~text
Celery deploy task
  -> DeployService.execute()
  -> per-Service advisory lock
  -> StateManager ownership/fencing
  -> immutable ServiceRevision
  -> native DeploymentPlan
  -> DeploymentLifecycleExecutor
  -> RuntimeContract
  -> SwarmRuntimeAdapter
  -> SwarmRuntime
  -> readiness
  -> canonical activation + terminal transition
~~~

The old Deploy facade / DeploymentOrchestrator remains only for the explicit
non-Swarm compatibility path (SWARM_ENABLED=0). It is not constructed on the
normal Swarm execution path.

## Plan/runtime boundary

SwarmRuntimeAdapter consumes the native DeploymentPlan and compiles it to a
typed SwarmExecutionSpec. It does not require DeploymentConfig and does not use
DeploymentPlanCompatibilityCompiler.

The transient DeploymentConfig used inside the native build path is a
Dockerfile-generation/build DTO only; it is not the RuntimeContract input.

## Release and artifact model

BuildCacheArtifact remains tied to build-cache retention and garbage
collection. BuildArtifact represents immutable application artifact identity
using a digest plus source/build/base-image provenance.

A Release is an immutable promotable snapshot referencing a ServiceRevision and,
when available, a BuildArtifact. Multiple Deploy attempts may reference the
same Release.

The existing Deploy.release_id remains the historical per-attempt UUID for
backward compatibility. Deploy.release_reference is the new reusable Release relationship.

Rollback targets an existing Release/artifact rather than rebuilding source
solely because the operation is a rollback.

## Activation and fencing

Worker identity remains the task id plus persisted heartbeat and lifecycle
generation. State mutations continue through StateManager.

Successful native execution reaches the canonical
activate_revision_and_succeed boundary. That transaction activates the
revision and promotes the associated Release. A stale worker cannot activate
newer desired intent.

## Runtime operation identity and cancellation

Native runtime mutations receive semantic operation keys. Runtime apply,
readiness and rollback carry cancellation callbacks.

Swarm readiness checks cancellation during its polling loop, rather than only
before entering the wait.

## Swarm capabilities

The Swarm adapter reports a replica capability of 0..8, matching the concrete
runtime validator.

Process graphs are applied through SwarmRuntime.apply_processes(). Each enabled
process gets a distinct managed Swarm service while the adapter keeps process
service names on the RuntimeHandle for readiness.

## Reconciliation

ReconciliationPlanner remains pure: it compares desired and observed state and
never calls Docker or mutates Django.

Runtime observations do not invent desired state. Missing revision identity
remains an unknown identity rather than becoming the desired revision based on
resource naming.

The scheduled monitor remains a compatibility integration point around the
runtime observation model; destructive actions still require managed runtime
identity.

## Security

Source archives retain traversal/symlink/member/size protections and secure
Docker build-context handling.

Runtime and Release JSON stores use redacted secret representations.
Build provenance contains digests and metadata, not plaintext secret values.

Build-scoped secrets remain rejected by the current build backend. No secret is
introduced through ARG, ENV, Dockerfile literals, labels, events or provenance.

## Storage and multi-node behavior

Logical service volume allocation is distinct from measured Docker usage and
does not imply hard filesystem quota.

Node-local persistent volumes remain node-local. Placement must honor the volume
owner pin or a genuinely shared storage backend; the cluster must not silently
treat a same-named local volume on another node as the same data.

For a multi-node Swarm deployment, an application image must be published to a
usable registry or the runtime must fail closed rather than assuming a
daemon-local image is cluster-wide.

## Failure and terminal semantics

User cancellation, timeout, stale ownership, runtime failure, rollback failure
and cleanup failure remain separate failure domains.

Terminal Deploy transitions continue to use the canonical state transition
boundary and deployment event outbox.

## Migration compatibility

The Release/BuildArtifact schema migration is additive and DB-only. It does not
require Docker, Celery, Redis, a registry or network access.

The non-Swarm legacy facade remains intentionally isolated until its remaining
production callers are removed.

## Known remaining compatibility areas

The native Swarm lifecycle is the primary execution path, but the repository
still contains the legacy non-Swarm facade and concrete scheduler compatibility
code. They are not alternate sources of Service authority.

Generic release-command execution outside the supported runtime-entrypoint path, canary/blue-green traffic splitting, and remote-only artifact-registry pulls remain explicitly unsupported. The native Laravel migration is represented as a `ReleaseSpec` and runs in the candidate runtime entrypoint; unsupported generic backends are blocked rather than simulated.
