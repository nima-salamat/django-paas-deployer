# PassDeployer Architecture

PassDeployer is a service-centric Docker PaaS control plane whose application runtime is Docker Swarm.

The control plane may itself run with Docker Compose, but user workloads are represented as Docker Swarm Services. The Swarm manager is the runtime control point; Docker owns task scheduling, restart and placement.

## Core ownership

Service owns source, build/runtime configuration, environment, secrets, processes, endpoints, networks, volumes and database bindings.
ServiceRevision is an immutable executable snapshot and owns the deployable source artifact.
Deploy is an execution operation linked to a revision and keeps historical/provenance state.
Service.desired_state is the declarative lifecycle target.
Swarm Service/Task state is observed runtime and is never the configuration source of truth.

## Execution flow

```
input representation
    -> normalize/validate
    -> Service
    -> ServiceRevision
    -> ServiceRuntimeGraph
    -> Dockerfile/image build
    -> Compose/Stack-shaped runtime specification
    -> Docker Swarm Service
    -> Docker Task
    -> Traefik / published networking
```

Supported inputs include archive/Git, Dockerfile, existing image, Compose and catalog definitions.
Compose is an input/runtime specification format. `docker compose up` is not used to start tenant application workloads.

The platform currently supports one running replica per application process. A stopped service may be represented by Swarm Services scaled to zero.

## Docker Swarm topology

One PassDeployer installation uses one shared Swarm cluster.

```
Swarm
├── app-a-web
├── app-a-worker
├── app-b-web
├── app-c-web
└── app-c-scheduler
```

A PassDeployer Service can therefore contain multiple ServiceProcess definitions while remaining one logical application in the control plane.

For each enabled process:

```
ServiceProcess
    -> Docker Swarm Service
        -> 1 Docker Task
```

The control plane does not create a separate Swarm per application.

## Service

User-owned deployable workload and lifecycle state.

## ServiceProcess

Web, worker, scheduler or custom executable process. Each process is an independent Swarm Service. Process environment and endpoints are compiled from the active revision graph. Replica counts greater than one are currently rejected.

## ServiceRevision

Immutable snapshot containing source/build/runtime metadata, processes, endpoints, volumes, networks, environment metadata and versioned secret references.

## Deploy

Execution operation and compatibility/API record. New executable changes create a Deploy and a new Revision.

Deploy is not the application runtime object. It records the operation that asks the Swarm runtime to converge to a revision.

## Runtime graph

`deployments.core.runtime_graph.ServiceRuntimeGraph` converts a revision into Docker-neutral runtime semantics.

`deployments.core.swarm.SwarmRuntime` converts that graph into a Compose/Stack-shaped specification and then creates or updates the real Docker Swarm Services through the Docker SDK.

This deliberately separates:

- Dockerfile: build artifact generation
- Compose/Stack specification: normalized runtime declaration
- Swarm Service: durable Docker runtime desired state
- Task/container: actual execution unit

## Swarm nodes

The Deploy app stores operator-facing `SwarmCluster` and `SwarmNode` records.

Docker remains the source of observed node state. Wagtail stores operator desired state such as:

- node availability: active, pause, drain
- node labels used for placement

A periodic reconciliation task reads Docker node state and applies those desired settings.

Node manager/worker promotion and demotion are intentionally not exposed as ordinary form fields; cluster topology changes remain explicit infrastructure operations.

## Placement

Revision runtime options may contain allow-listed Swarm placement constraints such as:

```
node.labels.region == eu
node.labels.storage == ssd
node.role == worker
```

Arbitrary Docker host settings are not accepted.

## Image distribution

A single-node Swarm can schedule a locally built image because the manager is also the execution node.

A multi-node Swarm requires a registry configured through `SWARM_IMAGE_REGISTRY`. The deployment worker publishes the immutable image before Swarm schedules the task.

Failing closed here is intentional: silently scheduling a worker that cannot pull the image would leave the deployment permanently pending.

## Networking

Application networks used by Swarm workloads are overlay networks.

The public routing path for the current installation is:

```
Internet
  -> host Nginx / TLS termination
  -> local Traefik
  -> proxy_net (overlay)
  -> Swarm Service
  -> Task
```

Traefik uses both its normal Docker provider for the PassDeployer control plane and its Docker Swarm provider for application Services.

Swarm routing labels are attached to the Swarm Service itself and include an explicit load-balancer target port.

TCP/UDP published endpoints use the Swarm ingress routing mesh. HTTP/HTTPS/WS application routes are handled by Traefik.

## Persistent volumes

Docker local volumes are node-local.

When a multi-node workload uses local volumes, the current runtime pins the service to the manager node that performed the build/deploy unless an explicit node-id constraint already exists.

This protects correctness but is not shared-storage HA.

A shared volume driver/storage backend should be added before attempting storage mobility between nodes.

## Secrets

Secrets are versioned and encrypted at rest. Revisions contain exact secret references, never plaintext.

Build-scoped secrets are currently rejected because the active image build backend uses Docker build arguments rather than BuildKit secret mounts. Runtime secret support is first-class.

## Databases

DatabaseResource represents a managed/external database resource. ServiceDatabaseBinding connects a workload Service to that resource.

Database provisioning still has a specialized DBDeployer because database initialization requires engine-specific readiness and credential reconciliation, but its runtime is now also a Docker Swarm Service. MySQL/MariaDB credential reconciliation executes against the live Swarm task container; persistent local volumes pin the database Service to the appropriate node.

## Reconciliation

The background monitor treats Docker Swarm Service/Task state as observed reality.

```
Service.desired_state
        |
        v
active ServiceRevision
        |
        v
Swarm Service
        |
        v
Task state
        |
        +--> reconcile back to desired state
```

Stale deployment recovery uses Swarm Service labels and task state rather than assuming a particular container name.

## Stop / delete

Stopping an application sets its desired state to `stopped` and scales its managed Swarm Services to zero.

Deleting a Service removes its managed Swarm Services before the legacy container cleanup path runs.

Deletion lifecycle/garbage collection remains an area for further durability work.

## Rollback

Rollback creates a new deployment operation targeting an existing immutable revision. It does not rewrite historical Deploy configuration.

Swarm update/rollback policies are configured conservatively: one task updated at a time and automatic rollback on failed updates.

## Shell limitation in multi-node mode

Docker Swarm exposes service/task lifecycle through the manager, but an interactive `docker exec` still executes against a container on a specific Docker Engine node.

The current shell implementation can exec into a running task when that task is on the connected Docker node. If the task is on another node, it returns a clear error instead of pretending the manager can exec remotely.

A future multi-node shell transport can connect directly to the task's node over a secured Docker SSH/TLS transport.

## Transitional compatibility

`selected_deploy` remains a compatibility projection for older APIs and records.
The active runtime source of truth is `Service.active_revision` plus `Service.desired_state`.
Legacy container orchestration remains only as an explicit fallback when `SWARM_ENABLED=0`.

## App catalog

`app_catalog` owns templates, variants, Compose normalization and multi-service dependency coordination. Child Services use the normal ServiceRevision -> Swarm runtime pipeline.

## Installation

See [install.md](../install.md) for:

- single-node Swarm initialization
- manager/worker joining
- registry configuration
- overlay networking
- Traefik integration
- Wagtail node management
- one-replica runtime behavior
- troubleshooting
