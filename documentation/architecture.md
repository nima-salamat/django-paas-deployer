# Architecture

PassDeployer is a service-centric Django PaaS whose application runtime is Docker Swarm.

## Ownership

```text
Service
  -> ServiceRevision
  -> ServiceRuntimeGraph
  -> Docker image / external image
  -> Docker Swarm Service
  -> Docker Task
```

- **Service** owns durable user intent and lifecycle state.
- **ServiceProcess** represents an executable process such as web, worker or scheduler.
- **ServiceRevision** is an immutable executable snapshot.
- **Deploy** is an execution operation and provenance record.
- **Swarm Service/Task** is observed runtime.

`selected_deploy` remains only as a compatibility projection. The runtime source of truth is the active revision plus desired state.

## Process model

One logical Service can contain multiple ServiceProcess rows. Every enabled process becomes one real Swarm Service.

The platform currently supports exactly one replica per process. A process requesting another replica count is rejected at validation/compiler/runtime boundaries.

## Control plane versus workload plane

The PassDeployer control plane may run with Docker Compose. Tenant workloads do not use `docker compose up`.

```text
HTTP / WebSocket
    -> Django / DRF / Channels
    -> Celery
    -> deployment engine
    -> Docker Engine / Swarm manager
    -> Swarm Service
    -> Task
```

## Reconciliation

The database stores desired state and deployment provenance. Docker reports observed service/task state. Periodic reconciliation repairs missed events, worker failures, daemon restarts and external Docker changes.

## Networking

The normal public path is:

```text
Internet
 -> host Nginx / TLS
 -> Traefik
 -> proxy_net overlay
 -> Swarm Service
 -> Task
```

Traefik's Swarm provider reads service labels.

## Nodes

One PassDeployer installation uses one shared Swarm cluster. Wagtail stores operator desired node availability/labels; Docker remains authoritative for observed node state.

## Storage

Docker local volumes are node-local. Multi-node services using local volumes are pinned to the node owning the data by default. This is a correctness policy, not shared-storage HA.

## Images

Multi-node application image distribution requires `SWARM_IMAGE_REGISTRY`. A deployment fails closed if the image cannot be distributed safely.

## Databases

Managed database workloads also run as Swarm Services. The specialized database layer performs engine-specific initialization and credential reconciliation while Swarm owns runtime scheduling.

## Transitional mode

`SWARM_ENABLED=0` remains an explicit legacy compatibility mode. The normal runtime is Swarm-first.
