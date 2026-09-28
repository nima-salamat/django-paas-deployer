# deploy

## Purpose

deploy is the persistent deployment/control-plane boundary. It stores Deploy attempts, deployment event history, base runtime image registry/leases and operator-visible Swarm metadata.

## Why this boundary exists

Workers and APIs need durable operation identity, provenance and infrastructure registry state. Docker resources themselves remain runtime state owned by deployments/runtime adapters.

## Responsibilities

Deploy and DeployLog persistence; base runtime image registry and leases; SwarmCluster/SwarmNode operator state; deployment APIs/download/export; DB routing for the deployment-log database; Wagtail administration.

## Non-responsibilities

Service desired configuration belongs to services. Deployment algorithm/runtime execution belongs to deployments. Runtime service logs belong to logs.

## Entity roles

Deploy = one execution/provenance attempt. DeployLog = lifecycle event record stored in the separate deployment-log database. BaseRuntimeImage = operator-owned shared build artifact registry row. BaseRuntimeImageLease = protection while an application deployment uses a base image. SwarmCluster/SwarmNode = operator desired/observed infrastructure metadata.

## API and serializers

See api.md and serializers.md. In particular, deploy serializers intentionally redact sensitive database/catalog-generated values on reads while allowing complete structured write input when authorization permits.

## Background behavior

See background.md and the deep deployment docs. A PENDING/BUILDING base-image row is not proof that an incompatible rebuild is required: a compatible local image with matching definition fingerprint can be reused.

## Invariants

1. Deploy is not desired state.
2. revision references an immutable ServiceRevision when present.
3. deployment logs are isolated in a separate DB and use scalar ids/no cross-database FK constraints.
4. base-image reuse is definition-fingerprint driven and leases protect in-use images.
5. operation resource identity is recorded so recovery can target the correct runtime resource.
6. operator desired node state and observed Docker state are distinct.

For execution semantics always continue to ../../deployments/README.md.
