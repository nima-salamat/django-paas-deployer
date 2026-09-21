# app_catalog

## Responsibility
Template/catalog installation and application-level multi-service coordination.

It owns catalog definitions, variants, Compose normalization, application installations and dependency ordering. It does not replace Service deployment execution.

## API
GET /api/application-catalog/apps/
GET /api/application-catalog/apps/<catalog_id>/
POST /api/application-catalog/apps/<catalog_id>/resolve/
GET/POST /api/application-catalog/installations/
GET /api/application-catalog/installations/<uuid:pk>/
DELETE /api/application-catalog/installations/<uuid:pk>/
POST /api/application-catalog/installations/<uuid:pk>/cancel/

## Compose
plan_from_compose() is an input adapter. Supported Compose semantics are normalized into ApplicationPlan and then into Service-domain resources.

## Secret policy
New catalog installations do not persist resolved plaintext secrets in ApplicationInstance.secret_config. ServiceSecret versions are used instead. Secrets are rejected when a catalog tries to bake them into Dockerfile/build files.

## Legacy migration

Existing catalog installations can be backfilled with:\n\n    python manage.py migrate_service_domain\n\nUse --application <uuid> to migrate one installation. The command is conservative: it creates ServiceRevision resources but does not delete legacy ApplicationInstance data.\n