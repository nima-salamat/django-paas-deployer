# logs

## Responsibility
Deployment/runtime log collection, retention, usage reconciliation, deployment-log database access and logging health.

## API exposure
There is no standalone /logs/ REST router. Service and admin endpoints expose the logging functionality:
GET /services/service/<uuid:pk>/logs/
GET /services/service/<uuid:pk>/logs/export/
GET /services/admin/logging/health/

## Storage
Deployment logs use the configured deployment-log database and raw IDs instead of cross-database foreign keys.
