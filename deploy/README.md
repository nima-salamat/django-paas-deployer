# deploy

## Responsibility
Stores deployment operations, lifecycle state, deployment logs and operator runtime-image metadata.

Service owns desired state. ServiceRevision owns immutable executable state. Deploy represents the execution operation.

## API
GET/POST /deploy/
GET/PUT/PATCH/DELETE /deploy/<uuid:pk>/
POST /deploy/<uuid:pk>/start/
POST /deploy/<uuid:pk>/cancel/
POST /deploy/<uuid:pk>/redeploy/
POST /deploy/<uuid:pk>/rebuild/
POST /deploy/<uuid:pk>/rollback/
PATCH /deploy/<uuid:pk>/update_db_config/
GET /deploy/<uuid:pk>/reveal_db_credentials/
GET /deploy/<uuid:pk>/logs/
GET /deploy/<uuid:pk>/logs/export/
GET /deploy/<uuid:pk>/download/
GET /deploy/name_is_available/
POST /deploy/set_deploy/
POST /deploy/unset_deploy/
POST /deploy/generate_db_credentials/
POST /deploy/inspect_zip/
POST /deploy/config_contract/

## Revision rule
Once a Deploy has a revision, executable inputs are immutable. A new executable configuration is a new Deploy plus a new ServiceRevision.
