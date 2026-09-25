# Testing and Security

## Test layers

The project contains unit/compiler tests, Django/API tests, regression contracts and optional Docker/Celery integration tests.

CI architecture validation compiles the full `src/` tree.

## Swarm contracts

Runtime tests cover single-replica enforcement, healthchecks, resource limits, placement constraints, UDP publication and multiple HTTP endpoints.

## Security boundary

Tenant data must not become privileged Docker execution, arbitrary devices/capabilities, host networking, arbitrary bind mounts, Docker socket access, unrestricted host-port publication or uncontrolled resources.

Archive extraction must reject traversal and unsafe symlink behavior.

## Failure policy

Unsupported capabilities should fail closed. Do not silently approximate a security or runtime boundary.
