# Deployment Engine

The `deployments` package performs asynchronous execution that the Service domain only describes.

## Responsibilities

- Celery deployment tasks
- source/build orchestration
- image building
- runtime graph compilation
- Swarm Service creation/update/removal
- readiness/health
- database runtime provisioning
- logs and cleanup
- reconciliation
- platform detection

## Lifecycle

1. Validate target Service/revision.
2. Resolve source/build inputs.
3. Build or select an image.
4. Produce the runtime graph.
5. Apply Swarm Services.
6. Wait for readiness.
7. Activate the revision.
8. Record success/failure.

## Ownership

The Deploy model is history/provenance. The Service and active ServiceRevision own desired executable state. The Swarm Service owns Docker runtime scheduling.

## Compatibility

Direct container runtime code remains behind `SWARM_ENABLED=0` only.
