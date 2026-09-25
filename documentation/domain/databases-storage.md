# Databases and Storage

## Database resources

`DatabaseResource` describes a managed/external database resource. `ServiceDatabaseBinding` connects it to an application Service.

## Runtime

Managed database engines also run as Swarm Services.

The database layer remains specialized for image selection, initialization, readiness and credential reconciliation, but Swarm owns runtime scheduling.

## MySQL/MariaDB

Credential reconciliation runs against the actual ready Swarm task container.

## Local storage

Docker local volumes are node-local. Services using them are pinned to the volume owner unless an explicit node-id rule overrides the placement.

## Reinitialization

Database `force_reinit` removes/recreates managed data volumes and must be treated as destructive.
