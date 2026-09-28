# 01 — System model

## Purpose

Define the nouns that deployment code moves between. When changing a deployment class, first identify which model or value object owns the fact being changed.

## Core entities

### Service

services.models.Service is the durable workload identity and declarative owner.

It carries user/service intent such as source kind/configuration, build/runtime configuration, network association, lifecycle status, desired runtime state, and pointers to the active revision.

A Service is **not** the Docker runtime object. Deployment code may derive a Docker name with Service.get_docker_service_name(), but the Docker object remains infrastructure state.

Important compatibility field:

- selected_deploy is a legacy projection.
- Runtime authority is Service.active_revision.
- services.revisioning.get_active_revision() can perform a one-way compatibility bridge from a successful selected deployment when active_revision is absent.

### ServiceProcess

services.models.ServiceProcess is part of declarative process intent.

It represents a named process such as web or a custom worker, with command/entrypoint, health check, environment and metadata. The current model constrains replicas to one per process.

The deployment runtime compiles each enabled process into a runtime process specification. In Swarm mode each process becomes an independent Swarm Service.

### ServiceRevision

services.models.ServiceRevision is an immutable executable snapshot.

A revision captures the effective source/configuration needed to reproduce a deployment without depending on mutable Service fields or the original Deploy row. The revision contains snapshots for configuration, processes, secrets, source/build/runtime/environment/endpoints/volumes/networks and a runtime graph snapshot.

The revision owns the copied deployment artifact where applicable; the historical source_deploy relationship is provenance, not the reproducibility source.

### Deploy

deploy.models.Deploy is one execution/provenance record.

It records the target Service, the revision being executed, historical input/version/upload, lifecycle status/stage/progress, base-image and application timing, execution task ownership and heartbeat, previous deployment, health/image/container/volume/network diagnostics, cancellation, rollback and recovery metadata.

A Deploy is not desired state. It is the record of one execution attempt.

### DeploymentPlan

deployments.planning.plan.DeploymentPlan is an immutable in-memory normalized execution description.

It combines RuntimeIdentity, RuntimeSelection, ServiceRuntimeGraph, image identity, environment and secret references, network/volume/endpoint specs, resources, placement, health/rollout/retry/logging policy, configuration provenance and an optional rollback plan.

The plan is an execution description, not a database model.

### ServiceRuntimeGraph

deployments.core.runtime_graph.ServiceRuntimeGraph is the compiled process/runtime graph.

It captures source/build/runtime metadata plus process, endpoint, volume and network relationships. ServiceRuntimeGraph.from_revision() reconstructs the graph from revision snapshots and keeps the revision id/number attached for correlation.

### Runtime identity and selection

deployments.runtime.identity.RuntimeIdentity provides stable identifiers for a runtime resource: service id, deployment id, revision id, process name and optional runtime resource name.

deployments.runtime.contract.RuntimeSelection describes the chosen backend, cluster, required capabilities and current availability.

Runtime backend choice is operator/infrastructure policy. Tenant configuration must not be allowed to select host infrastructure.

### Runtime backend

The runtime backend is represented by RuntimeContract. It exposes operations such as apply, inspect, wait_ready, stop, remove, rollback and logs.

The current concrete backend is Docker Swarm. The legacy Docker-container runtime survives only as a compatibility execution path when Swarm is disabled.

### Swarm Service and Task

A Docker Swarm Service is the actual long-lived runtime resource. A Swarm Task is a scheduled instance of that service.

The current implementation supports replicated mode, exactly 0 or 1 replica at runtime, one running replica as the readiness invariant, and process-to-service mapping.

For an application with no explicit process graph, the runtime synthesizes a web process.

### Database deployment entities

Database resources are represented in the service/domain layer by DatabaseResource and ServiceDatabaseBinding. Database workloads still enter the deployment subsystem but use a specialized DBDeployer path.

The database runtime is therefore part of the common deployment architecture, while image/init/credential/readiness details are intentionally specialized.

### BaseRuntimeImage

deploy.models.BaseRuntimeImage is operator-owned reusable runtime infrastructure.

Identity includes logical runtime + runtime version + variant + architecture + docker host.

The row tracks the image reference, image id/digest, definition fingerprint, lifecycle status, build owner/task, rebuild request and failure diagnostics.

A BaseRuntimeImageLease protects a shared image from cleanup while a deployment is using it.

## Desired, immutable, execution and observed state

~~~text
Mutable user intent
    Service / ServiceProcess
          |
          v
Immutable executable intent
    ServiceRevision
          |
          v
Execution/provenance
    Deploy
          |
          v
Compiled execution
    DeploymentPlan / RuntimeGraph / DeploymentConfig bridge
          |
          v
Observed infrastructure
    Swarm Service / Task / runtime observations
~~~

Do not reverse these ownership relationships.

A bug fix that changes user intent belongs in the service/domain layer; a bug in Docker behavior belongs in runtime/orchestrator code; a bug in lifecycle persistence belongs in state management.

## Activation and compatibility projection

Activation is not “set any successful Deploy as current”.

DeployService captures previous_deploy_id. Its activation callback locks the Service and verifies that the active deploy still matches the expected previous deployment before calling activate_revision_locked().

activate_revision_locked():

1. marks the prior active revision superseded;
2. marks the new revision active;
3. updates Service.active_revision;
4. updates selected_deploy as a legacy compatibility projection.

A stale worker must not activate over a newer deployment.

## What each entity must not do

- Service must not perform Docker operations.
- ServiceRevision must not become a mutable configuration bucket.
- Deploy must not be treated as authoritative desired service configuration.
- DeploymentPlan must not perform Docker calls.
- RuntimeObservation must not mutate desired state by itself.
- BaseRuntimeImage must not contain tenant application source or dependencies.

## Related code

- src/services/models.py
- src/services/revisioning.py
- src/deploy/models.py
- src/deployments/core/runtime_graph.py
- src/deployments/planning/plan.py
- src/deployments/runtime/identity.py
- src/deployments/runtime/contract.py
- src/deploy/base_images.py
