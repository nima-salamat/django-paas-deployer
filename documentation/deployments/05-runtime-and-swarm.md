# 05 — Runtime and Swarm

## Purpose

Separate runtime-neutral concepts from Docker/Swarm implementation so future changes do not leak infrastructure concerns into domain or planning code.

## Runtime-neutral contract

The runtime package contains:

- RuntimeIdentity: stable resource identity;
- RuntimeSelection: backend/cluster/capability/availability choice;
- RuntimeCapabilities: features a backend supports;
- RuntimeAvailability: whether it can execute now;
- RuntimeObservation: normalized observed status/task information;
- RuntimeContract: operations available to lifecycle code;
- RuntimeRegistry: backend selection/composition.

Capabilities and availability are deliberately separate:

~~~text
capabilities = what the backend can do
availability = whether it can do it now
~~~

## Runtime selection

RuntimeRegistry._resolve_backend() reads infrastructure policy only.

Selection sources are operator policy, cluster policy, explicit bootstrap backend setting, legacy SWARM_ENABLED, then the Swarm default.

Service/Revision/Deploy tenant fields must not choose host infrastructure.

## Current Swarm implementation

The concrete implementation remains deployments.core.swarm.SwarmRuntime.

The newer deployments.runtime.swarm.adapter.SwarmRuntimeAdapter wraps that implementation to expose RuntimeContract operations. It is a migration seam, not a second runtime.

The current main orchestrator directly invokes SwarmRuntime.apply_processes() when Swarm is enabled.

## Runtime invariants

The current Swarm runtime supports replicated services, exactly one running replica per enabled process, process graph execution, overlay networks, persistent volume mounts, node placement constraints, rolling-update/rollback configuration, healthchecks, service logs and managed labels.

A requested replica count other than 0/1 fails runtime validation.

The data model also constrains ServiceProcess.replicas to one.

## Process-to-service mapping

SwarmRuntime.apply_processes() turns each enabled ServiceProcess into an independent Swarm Service.

Naming rule:

- web uses the canonical Service runtime name;
- other processes use a suffix based on process name.

If no process list is supplied, the runtime synthesizes a default web process from the top-level start command/entrypoint.

Each process receives merged environment and resource settings. Process-specific health and placement metadata are applied.

## Networking

Runtime endpoints are represented with EndpointSpec.

Public HTTP/HTTPS/WebSocket endpoints can produce Traefik-facing labels on managed services.

Network compilation remains a runtime concern because Docker network existence/attachment is infrastructure state.

## Volumes

Managed persistent volumes are prepared before runtime application.

When Swarm uses node-local volumes, SWARM_LOCAL_VOLUME_PIN can enforce node placement on the node that owns the local volume.

The runtime rejects unsafe local-volume/node mismatches rather than silently creating a same-named local volume on another node.

The higher-level volume manager also requires an owning Service for persistent volume accounting.

Do not turn this into arbitrary tenant host bind support.

## Resources

Runtime CPU/RAM limits come from resolved server policy and Service Plan values.

The Swarm runtime translates them to Docker Engine resource structures.

Tenant build/runtime config does not directly control cgroup limits.

## Placement

Supported placement constraints are intentionally narrow and validated against fields such as node id, hostname, role, platform OS/arch and node labels.

Arbitrary Swarm constraint expressions are not a supported tenant contract.

## Images

Application deployment builds an application image first.

Swarm receives that image reference. When a registry is configured, the Swarm runtime may publish the image to the configured registry/namespace before creating/updating the service so other nodes can pull it.

The runtime itself does not rebuild the application image.

## Readiness

The Swarm runtime considers a service ready when replicas_desired == 1 and replicas_running == 1.

If a task enters failed/rejected state, readiness fails with task diagnostics.

Runtime-level readiness is distinct from application HTTP health semantics.

## Service lifecycle operations

Current runtime operations include create/update, inspect, wait for readiness, stop, remove, rollback through re-apply of a known plan/config, service logs and legacy-container cleanup after Swarm activation.

When Swarm is enabled, restart/rollout semantics belong to the Swarm Service/Task layer rather than manually stopping and starting an individual container.

## Labels and identity

Managed Swarm services carry labels including managed-by, PassDeployer service/deployment/process identity, allowed deployment labels and endpoint/router labels where public routing exists.

Reconciliation relies on identity labels when proving that an observed resource belongs to a particular deployment.

A recovery routine must never treat an unowned same-name service as authoritative merely because it is running.

## Legacy runtime

RuntimeBackend.LEGACY_DOCKER remains as a compatibility option.

It is used when SWARM_ENABLED=false. The legacy path is based on Docker containers and snapshot/rename/replace/restore behavior.

The Docker event consumer is also legacy-only in Compose: its service is under profile legacy-runtime.

Do not introduce new Swarm functionality into the legacy container manager or vice versa.

## Runtime boundary rule

**Runtime code owns Docker calls.**

**Reconciliation decides; runtime executes.**

Planning, domain models, configuration resolution and reconciliation decisions must not call Docker directly.

## Related code

- src/deployments/runtime/contract.py
- src/deployments/runtime/registry.py
- src/deployments/runtime/capabilities.py
- src/deployments/runtime/observations.py
- src/deployments/runtime/swarm/adapter.py
- src/deployments/core/swarm.py
- src/deployments/core/orchestrator.py
- src/deployments/core/manager/
