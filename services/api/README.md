# services/api

## Responsibility
This package exposes the HTTP boundary for the Service domain.

Configuration endpoints are declarative. They update desired Service state; they do not call Docker directly.

## Endpoints
Service configuration: GET/PATCH /services/service/<uuid:service_id>/configuration/
Environment: GET/POST/DELETE /services/service/<uuid:service_id>/environment/
Secrets: GET/POST/DELETE /services/service/<uuid:service_id>/secrets/
Endpoints: GET/POST/DELETE /services/service/<uuid:service_id>/endpoints/
Networks: GET/POST/DELETE /services/service/<uuid:service_id>/networks/
Database resources: GET/POST /services/service/<uuid:service_id>/database-resources/
Database bindings: GET/POST/DELETE /services/service/<uuid:service_id>/databases/
Revisions: GET /services/service/<uuid:service_id>/revisions/
Revision detail: GET /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/
Revision rollback: POST /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/rollback/

## Security
Secret values are never returned from revision APIs. Sensitive keys in source/build/runtime JSON are rejected and must be modeled as ServiceSecret-backed environment variables.
