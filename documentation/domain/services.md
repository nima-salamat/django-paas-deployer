# Service Domain

## Service

Service is the durable user-owned workload. It owns desired lifecycle state, build/runtime intent, process definitions, active revision, environment, secrets, endpoints, networks, volumes, database bindings, sharing and shell policy.

## ServiceProcess

A process represents one executable workload such as web, worker, scheduler or custom.

It carries command, entrypoint, environment, healthcheck, resource and placement intent.

## ServiceRevision

A revision is an immutable executable snapshot. Changing executable inputs produces a new revision.

## Deploy

Deploy is an execution operation/provenance record. It does not own runtime.

Legacy `selected_deploy` remains only as a compatibility projection.

## Boundary

Service APIs are declarative. Docker operations belong in `deployments`.
