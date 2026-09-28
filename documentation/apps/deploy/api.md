# deploy API

Root mount: /deploy/

Deploy APIs use SessionJWTAuthentication for normal customer operations and application-level ownership/share checks for Service actions.

| Method | Route | Behavior |
|---|---|---|
| GET, POST | / | DeployViewSet list/create. Querying is owner/service scoped; creation validates Service association, name uniqueness within Service and executable configuration. |
| GET, PUT, DELETE | /<uuid>/ | Retrieve/update/delete a Deploy subject to immutable revision semantics and ownership policy. Once a revision is attached, executable fields are not edited in place. |
| POST | /<uuid>/start/ | Queues deployment execution for that Deploy. |
| POST | /<uuid>/cancel/ | Requests cancellation of that Deploy. |
| POST | /<uuid>/redeploy/ | Creates/queues a new deployment operation using current Service intent as implemented by the endpoint. |
| POST | /<uuid>/rebuild/ | Requests rebuild execution without turning the current row into a mutable runtime definition. |
| POST | /<uuid>/rollback/ | Queues rollback to an earlier executable revision under the deployments rollback rules. |
| PATCH | /<uuid>/update_db_config/ | Updates allowed database deployment configuration with DB-specific validation. |
| GET | /<uuid>/reveal_db_credentials/ | Credential reveal is restricted by Service ownership/share permission and sensitive-config rules. |
| GET | /<uuid>/logs/ | Returns recent deployment lifecycle events from the deployment-log DB. |
| GET | /<uuid>/logs/export/ | Exports deployment events for an authorized Deploy. |
| GET | /<uuid>/download/ | Downloads deploy ZIP only for an authorized owner/staff user. |
| GET | /name_is_available/ | Checks deployment-name availability within the relevant Service scope. |
| POST | /set_deploy/ | Updates the Service compatibility selected_deploy projection through a locked Service operation. |
| POST | /unset_deploy/ | Clears the compatibility selected_deploy projection. |
| POST | /generate_db_credentials/ | Generates database credential config for authorized Service/Deploy context. |
| POST | /inspect_zip/ | Inspects an uploaded deployment archive without treating inspection as a deployment execution. |
| GET/POST | /config_contract/ | Returns the deployment configuration contract used by the current frontend/legacy boundary. |

## Important serializer policy

DeploySerializer exposes revision/provenance and status data. MaskedDBConfigField strips sensitive DB credentials for unauthorized viewers and additionally redacts sensitive keys/generated catalog secrets. DeploymentZipField validates uploaded archive size/type and participates in safe file ownership.

## Execution chain

start/redeploy/rebuild/rollback
 -> permission + Service lock/policy
 -> Deploy record/task ownership
 -> deployments Celery task
 -> revision/planning/runtime
 -> Deploy state/events updated

The API is not the Docker runtime owner.

Source: src/deploy/urls.py, apis.py, serializers.py.
