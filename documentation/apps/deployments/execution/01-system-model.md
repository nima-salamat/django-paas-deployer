# 01 — System model and ownership

## Purpose

This document defines the semantic types used by the deployment engine. Read it before changing models, revisioning, plans or runtime identity.

## State categories

```text
DESIRED / DECLARATIVE
  Service
  ServiceProcess

IMMUTABLE EXECUTABLE
  ServiceRevision

EXECUTION / PROVENANCE
  Deploy

COMPILED EXECUTION
  ServiceRuntimeGraph
  DeploymentPlan
  DeploymentConfig compatibility DTO

OBSERVED INFRASTRUCTURE
  RuntimeObservation
  Swarm Service / Swarm Task
```

The categories are intentionally different. Bugs often come from treating one as another.

## Service

**Path:** `src/services/models.py`

### Owns

- durable service identity;
- mutable source/build/runtime intent;
- process definitions;
- desired state;
- active revision pointer;
- network/volume/database associations.

### Entered from

Service APIs and service-domain operations.

### Consumed by

Revisioning and deployment composition.

### Why it exists

A Service represents what the user wants over time. It must remain mutable without changing a deployment that is already executing a frozen revision.

### Must not do

Service domain code must not directly perform Docker/Swarm operations.

## ServiceProcess

**Path:** `src/services/models.py`

### Owns

One logical process definition: name, process type, command/entrypoint, environment, healthcheck, resources and metadata.

### Preconditions

Belongs to a Service and has an allowed replica count.

### Output

Revisioning snapshots it and the runtime graph later turns each enabled process into a runtime process.

### Current invariant

The model/runtime currently supports one replica per process. Swarm execution rejects values other than one.

### Why it exists

A Service can have multiple independently executable processes without making the top-level Service model itself a Docker service specification.

## ServiceRevision

**Path:** `src/services/revisioning.py`

### Owns

An immutable snapshot of executable configuration/provenance: source, build, runtime, process, endpoint, volume, network, environment and secret references.

### Called by

`DeployService._execute_locked()` through `ensure_revision_for_deploy()`.

### Preconditions

Deploy and Service exist; the Deploy row is locked by the revisioning transaction.

### Output

A revision id and revision snapshots that can reconstruct the deployment independently of later mutable Service edits.

### Why immutability exists

Deployment work takes longer than an ordinary database transaction. If runtime generation reread mutable Service state after the build started, the image, runtime resource and activation could represent different configurations.

Immutability also makes rollback meaningful: a previous revision can be targeted without mutating history.

### What changes after creation

Service intent may change. Secrets may gain newer versions. A new Deploy may be created. The old revision must not change.

### Consumption boundary

`materialize_revision_config()` resolves the revision into the legacy DeploymentConfig-shaped mapping; `ServiceRuntimeGraph.from_revision()` reconstructs runtime-neutral process/endpoints/volumes/networks.

### Compatibility

`selected_deploy` is a legacy Service projection. `active_revision` is the authoritative active revision. The compatibility fallback exists so older successful deployment rows do not disappear from legacy readers.

### Must not do

Do not mutate a revision to “fix” a currently executing deployment. Create/execute a new revision instead.

## Deploy

**Path:** `src/deploy/models.py`

### Owns

One execution attempt:

- target Service;
- revision link;
- lifecycle status/stage/progress;
- execution task id and heartbeat;
- previous deploy;
- cancellation;
- health/image/container/network/volume diagnostics;
- phase timing;
- rollback metadata.

### Called by

Service/API code creates it; Celery tasks execute it; monitor/reconciliation observes it.

### Preconditions for normal execution

Deploy must be eligible for execution and its Service must pass the queue/state gate. The worker must acquire the Service advisory lock and task ownership.

### Output

A terminal result plus durable provenance/state.

### Why Deploy is not desired state

An execution attempt is ephemeral compared with Service intent. Multiple Deploy rows can exist for one Service.

## DeploymentPlan

**Path:** `src/deployments/planning/plan.py`

### Contract

Frozen normalized execution data consumed by a runtime boundary.

It contains RuntimeIdentity, RuntimeSelection, ServiceRuntimeGraph, image reference, environment, secret refs, networks, volumes, endpoints, resources, placement and policy.

### Preconditions

Compiler receives:

- runtime identity;
- graph;
- runtime selection;
- resolved configuration;
- non-empty image ref;
- valid strategy kind.

### Postcondition

The returned plan is immutable and its required capabilities are checked against the selected runtime.

### Why it exists

A runtime adapter should not need to reconstruct policy from several mutable sources. The plan is the handoff artifact.

### Must not do

A plan is data, not a service object. It must not call Docker or mutate Django state.

## ServiceRuntimeGraph

**Path:** `src/deployments/core/runtime_graph.py`

### Contract

Runtime-neutral compiled topology.

It contains processes, endpoints, volumes, networks and runtime/build metadata without Docker SDK objects.

### Called by

Current DeployService after revision materialization.

### Produces

A graph used to derive DeploymentPlan input and to populate legacy DeploymentConfig/runtime options.

### Why it exists

The same runtime semantics should be representable without baking Docker object types into every upstream layer.

## RuntimeIdentity

**Path:** `src/deployments/runtime/identity.py`

Identity is the correlation key for external runtime state: Service, Deploy, Revision, process and runtime resource name.

### Why it exists

The runtime needs stable identity to inspect the right resource and reconciliation needs identity to prove ownership. Resource name alone is insufficient.

## RuntimeSelection

**Path:** `src/deployments/runtime/contract.py`

It records:

- backend;
- cluster;
- required capabilities;
- actual capabilities;
- availability;
- selection reason.

### Important distinction

Capabilities answer **“can this backend support the request?”**

Availability answers **“can it execute now?”**

Do not collapse unsupported, disabled, unreachable and temporarily degraded into one state.

## RuntimeObservation

**Path:** `src/deployments/runtime/observations.py`

It reports what infrastructure observed:

- MISSING;
- PROVISIONING;
- READY;
- STOPPED;
- DEGRADED;
- FAILED;
- UNKNOWN.

It includes runtime/task ids, replica counts, revision identity if known and detailed observations.

### Must not do

An observation is read-only evidence. It must not become desired state merely because it is convenient.

## BaseRuntimeImage

**Path:** `src/deploy/models.py` + `src/deploy/base_images.py`

Operator-owned reusable runtime artifact keyed by runtime/version/variant/architecture/Docker host.

It is deliberately outside the ServiceRevision model because it is shared infrastructure, not tenant executable history.

## Swarm Service / Task

Swarm Service is the long-lived runtime resource; Task is an individual scheduled instance.

The current runtime supports one running replica per enabled process.

Runtime labels carry deployment/revision identity used by activation recovery and reconciliation.

## Activation semantics

Activation means changing the durable Service pointer to the new revision after runtime readiness.

Current callback in `DeployService._execute_locked()`:

1. locks Service;
2. gets current active Deploy;
3. checks it still equals `previous_deploy_id`;
4. calls `activate_revision_locked()`;
5. sets desired_state=running.

This prevents a worker that started earlier from overwriting a newer deployment's authority.

## Entity relationship summary

```text
Service
  ├── ServiceProcess*
  ├── ServiceRevision*
  ├── active_revision -> ServiceRevision
  └── Deploy*

Deploy
  ├── Service
  ├── revision -> ServiceRevision
  └── previous_deploy -> previous execution

ServiceRevision
  └── immutable snapshots

DeploymentPlan
  └── derived from revision graph + resolved policy

RuntimeObservation
  └── derived from Docker/Swarm reality
```

## Modification navigation

| Desired change | Change here | Not here |
|---|---|---|
| Service user intent | `src/services/` | Docker runtime |
| Freeze/rollback executable config | revisioning | runtime adapter |
| Process topology | ServiceProcess/revisioning/runtime graph | Swarm service code |
| Runtime backend identity | runtime contracts/selection | tenant config |
| Actual Docker resource behavior | runtime/core | Service model |
| Lifecycle state transition | state machine/StateManager | arbitrary model.save() |
