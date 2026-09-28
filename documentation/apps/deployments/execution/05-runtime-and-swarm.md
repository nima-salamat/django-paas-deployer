# 05 — Runtime and Swarm

## Purpose

Separate the semantic runtime contract from the current concrete Docker Swarm implementation.

The key rule is:

> Planning describes what should run. Runtime makes infrastructure do it. Observation reports what actually happened.

## Runtime layers

```text
DeploymentPlan
      |
      v
RuntimeSelection
      |
      v
RuntimeContract
      |
      v
SwarmRuntimeAdapter
      |
      v
core.swarm.SwarmRuntime
      |
      v
Docker Engine / Swarm
```

## RuntimeSelection

**Path:** `runtime/registry.py`, `runtime/contract.py`

### Called by

Current compatibility plan construction and the newer application lifecycle seam.

### Inputs

Operator policy, cluster metadata, optional capability requirements.

### Output

RuntimeSelection.

### Why backend selection is separate

A Service request may specify application behavior, but it must not select arbitrary host infrastructure.

The registry intentionally ignores `backend` fields on Service/Revision/Deploy tenant data.

### Availability

With `probe=False`, selection can remain UNKNOWN availability.

With `probe=True`, the adapter checks whether the runtime is active, reachable and manager-capable.

Do not interpret UNKNOWN as ACTIVE.

## RuntimeCapabilities

**Path:** `runtime/capabilities.py`

Capabilities describe what a backend supports:

- service scheduling;
- replicas;
- rolling update;
- rollback;
- node constraints;
- overlay networks;
- persistent volumes;
- service logs;
- health checks;
- process graph.

### Why capabilities exist

The plan compiler can reject impossible requests before making runtime changes.

## RuntimeAvailability

Availability describes:

- enabled/disabled;
- reachable/unreachable;
- manager-capable/degraded;
- reason code.

### Why separate it from capabilities

“Backend cannot do this” and “backend could do this but Docker is currently unavailable” have different recovery behavior.

## RuntimeContract

**Path:** `runtime/contract.py`

This is the semantic interface for a runtime backend.

### `apply(plan, operation_key)`

**Preconditions**

- caller has a resolved plan;
- plan capabilities are supported;
- caller has execution ownership;
- runtime is available.

**Semantics**

Make the external runtime represent the plan and return a RuntimeHandle.

**Postcondition**

A handle is returned if the operation succeeded.

### `inspect(identity)`

Returns observed runtime state for the requested identity.

It is observational and must not silently mutate desired state.

### `wait_ready(handle, timeout, cancel_check)`

Waits until backend-specific readiness is satisfied.

The caller must not treat a handle returned by apply as automatically ready.

### `stop(handle)` / `remove(handle)`

Perform explicit lifecycle actions against the identified runtime resource.

### `rollback(plan, target_plan)`

Restore a known-good target plan. A runtime backend should reject rollback when no explicit target is available.

### `logs(identity)`

Returns runtime logs/diagnostics; it is observational.

### Idempotency and operation keys

Runtime results expose `changed` and `idempotent`.

The fake runtime contract tests require repeating the same application operation to be recognized as idempotent rather than creating a duplicate logical resource.

The operation key is a stable correlation/idempotency input. A backend may use it to make repeated calls safe.

## RuntimeHandle

A handle carries:

- backend;
- RuntimeIdentity;
- runtime id;
- resource name;
- metadata.

### Why a handle exists

Later lifecycle operations must act on the resource returned by apply rather than rediscovering an arbitrary same-name resource.

## RuntimeObservation

**Path:** `runtime/observations.py`

### Status semantics

- MISSING: no managed runtime found;
- PROVISIONING: exists but not ready;
- READY: backend-level ready;
- STOPPED: intentionally not running;
- DEGRADED: exists but not fully healthy/ready;
- FAILED: runtime reports failure;
- UNKNOWN: insufficient observation.

### Ownership warning

An observation can tell you what exists, but identity fields determine whether it is yours.

## SwarmRuntimeAdapter

**Path:** `runtime/swarm/adapter.py`

### Why it exists

It is the migration seam that presents the old Swarm implementation through the RuntimeContract.

### Called by

RuntimeRegistry and runtime contract tests.

### Preconditions

SwarmRuntime must be available; plan must carry DeploymentConfig compatibility data and image ref for the current implementation.

### Output

RuntimeOperationResult + normalized RuntimeObservation/RuntimeHandle.

### Important behavior

Inspection does **not** automatically invent a revision id. If a managed revision label is absent, the observation retains unknown revision identity so reconciliation can fail closed.

### Must not do

Do not make this adapter a second independent Swarm implementation.

## Current concrete implementation: core/swarm.py

**Path:** `core/swarm.py`

The current production application path calls this class directly.

### It owns

- Docker Engine API interactions;
- Swarm service create/update/remove/stop;
- task inspection;
- image publication;
- network attachment;
- volume placement validation;
- healthcheck conversion;
- process-to-service mapping;
- service labels;
- runtime readiness.

### It consumes

A resolved DeploymentConfig/compiled process specifications.

It should not derive tenant security policy from raw request data.

## Process-to-Swarm-Service mapping

`SwarmRuntime.apply_processes()` maps each enabled process to an independent Swarm Service.

- `web` uses the canonical service runtime name;
- other process names receive service-name suffixes.

If the graph has no process list, a default web process is synthesized.

### Replica invariant

Every enabled process currently requires one replica. The runtime explicitly rejects anything other than 1.

## Network behavior

Runtime network semantics are based on EndpointSpec/NetworkSpec.

Public HTTP/HTTPS/WebSocket endpoints can produce Traefik labels and require proxy network integration.

The runtime, not the platform plugin, owns actual Docker network creation/attachment.

## Volume behavior

Persistent volumes are registry-backed.

`VolumeMountManager`:

- validates names and bind sources;
- rejects unregistered managed volumes;
- preserves size/accounting metadata;
- prevents accidental same-name local-volume creation when a required volume is missing on the connected node.

Swarm local-volume pinning can add a node.id constraint matching the local volume owner.

### Why

Docker local volumes are node-local. Allowing Swarm to recreate a same-named local volume on another node can silently create an empty data store.

## Placement

Placement constraints are intentionally validated.

Supported expressions cover node id/hostname/role/platform and labels. Arbitrary Docker constraint expressions are not a tenant contract.

## Images and distribution

The application image is built before runtime application.

When a Swarm image registry is configured, the runtime may publish the image to the configured registry namespace for multi-node pulls.

Runtime does not rebuild the application image.

## Readiness

Current Swarm-level readiness is:

```text
replicas_desired == 1
AND
replicas_running == 1
```

If a desired-running task fails/rejects, wait_ready raises a runtime error with task diagnostics.

This is backend readiness, not necessarily application HTTP readiness.

## Health and application readiness

In legacy container mode, `DockerHealthChecker` provides application-level checks.

In Swarm mode, the concrete runtime applies Docker HEALTHCHECK semantics and service/task state; public application readiness may additionally be represented by runtime health policy depending on the generated configuration.

Do not use “resource exists” as the readiness criterion.

## Labels and identity

Managed runtime labels carry service/deployment/process identity and routing information.

Reconciliation and stale-worker recovery use these labels as positive evidence of ownership.

A same-name resource without the expected identity is ambiguous.

## Legacy runtime

`RuntimeBackend.LEGACY_DOCKER` remains for `SWARM_ENABLED=false`.

It uses Docker container operations and snapshot/rename/restore patterns.

The event consumer is also legacy-only in Compose under the `legacy-runtime` profile.

### Why it remains

Compatibility, not architectural preference.

Do not add new Swarm semantics to the legacy container manager or assume legacy snapshot behavior exists in Swarm.

## How to use this layer

Use the runtime contract when implementing backend-neutral lifecycle behavior.

Use `core/swarm.py` when fixing the actual current Swarm Docker behavior.

Use the adapter when changing the migration seam.

Do not introduce a Docker call in planning simply because the runtime object is not convenient to reach.

## Related code

- `src/deployments/runtime/contract.py`
- `src/deployments/runtime/capabilities.py`
- `src/deployments/runtime/observations.py`
- `src/deployments/runtime/registry.py`
- `src/deployments/runtime/swarm/adapter.py`
- `src/deployments/core/swarm.py`
- `src/deployments/core/volumes.py`
- `src/deployments/core/manager/`
