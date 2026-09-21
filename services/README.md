# services

## Responsibility
The services app owns the user-facing Service domain: lifecycle, configuration, processes, revisions, environment variables, secrets, endpoints, networks, volumes, database bindings, sharing and restricted shell state.

It does not build images or run Docker lifecycle stages. deployments owns execution.

## Key models
Service, ServiceProcess, ServiceRevision, ServiceEnvironmentVariable, ServiceSecret, ServiceSecretVersion, ServiceEndpoint, ServicePortReservation, ServiceNetworkAttachment, DatabaseResource, ServiceDatabaseBinding and Volume.

## API base
Primary prefix: /services/

## Service CRUD
GET/POST /services/service/
GET/PUT/PATCH/DELETE /services/service/<uuid:pk>/

## Runtime operations
POST /services/start_service/
POST /services/stop_service/
POST /services/restart_service/
POST /services/force_cancel_deploy/
POST /services/purge_service_runtime/
GET /services/service_status/

## Configuration
GET/PATCH /services/service/<uuid:service_id>/configuration/
GET/POST/DELETE /services/service/<uuid:service_id>/environment/
GET/POST/DELETE /services/service/<uuid:service_id>/secrets/
GET/POST/DELETE /services/service/<uuid:service_id>/endpoints/
GET/POST/DELETE /services/service/<uuid:service_id>/networks/

## Revisions
GET /services/service/<uuid:service_id>/revisions/
GET /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/
POST /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/rollback/

Revision endpoints never return plaintext secret values.

## Database resources
GET/POST /services/service/<uuid:service_id>/database-resources/
GET/POST/DELETE /services/service/<uuid:service_id>/databases/

## Volumes and networks
GET/POST/PUT/PATCH/DELETE /services/volume/
POST /services/volume/<uuid:pk>/detach/
GET /services/volume/<uuid:pk>/files/
GET /services/volume/<uuid:pk>/download/
GET/POST/PUT/PATCH/DELETE /services/networks/

## Shell
Service shell HTTP APIs are under /services/services/<uuid:service_id>/shell/ and expose session, command, file, tree, audit, history, environment and health operations.

## Logs
GET /services/service/<uuid:pk>/logs/
GET /services/service/<uuid:pk>/logs/export/

## Sharing
Sharing APIs are under /services/services/mine/, /services/services/shared/, /services/services/unified/, /services/services/share/, /services/services/shares/, /services/services/groups/, /services/services/share-presets/ and the service access endpoint.

## Boundary
Do not add Docker client calls to this app. services records intent; deployments executes it.
