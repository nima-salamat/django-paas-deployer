# Architecture

PassDeployer is a service-centric Django PaaS whose application runtime is Docker Swarm.

> **Deployment architecture entry point:** read [deployments/README.md](deployments/README.md) before opening files under \`src/deployments/\`.

## Ownership

~~~text
Service
  -> ServiceRevision
  -> ServiceRuntimeGraph
  -> application image / external image
  -> Docker Swarm Service
  -> Docker Task
~~~

- Service owns durable user intent and desired runtime state.
- ServiceProcess represents an executable process.
- ServiceRevision freezes executable configuration.
- Deploy records one execution attempt/provenance.
- Swarm Service/Task is observed runtime infrastructure.

\`selected_deploy\` remains a compatibility projection. Active revision plus desired state is the current authority.

## Process model

One Service may contain multiple ServiceProcess rows. Enabled processes map to separate Swarm Services.

Current runtime execution supports one replica per process.

## Control plane

~~~text
HTTP / WebSocket
    -> Django / DRF / Channels
    -> Celery
    -> deployment engine
    -> Docker Engine / Swarm
    -> Service / Task
~~~

## Reconciliation

Desired state lives in the database. Runtime observation comes from Docker/Swarm. Reconciliation compares them and chooses repair.

See [deployments/07-reconciliation-and-recovery.md](deployments/07-reconciliation-and-recovery.md).

## Storage

Docker local volumes are node-local. The current runtime may pin local managed volumes to the owning node.

This is a correctness rule, not shared-storage high availability.

## Images

Application images are deployment artifacts. Base runtime images are operator-owned shared artifacts.

See [deployments/04-build-and-platforms.md](deployments/04-build-and-platforms.md) and [deployments/08-base-images.md](deployments/08-base-images.md).

## Databases

Managed database workloads use the common runtime architecture with specialized engine initialization/readiness.

See [deployments/10-database-deployments.md](deployments/10-database-deployments.md).

## Transitional mode

\`SWARM_ENABLED=0\` remains an explicit legacy compatibility mode. The normal runtime path is Swarm-first.
