# app_catalog serializers

## ApplicationInstanceSerializer

Read-oriented representation of a catalog installation. It exposes id/name/catalog/variant/software version, config, status/stage/errors, timestamps and child-service summaries.

secret_config is not returned as raw values. The API exposes which secret configuration slots are present (secrets_configured) so the UI can communicate that credentials exist without leaking generated secret material.

This serializer represents coordinator state, not the child Service or Deploy state.

## API mapping

POST /api/application-catalog/installations/
 -> ApplicationInstance input validation in view/service
 -> ApplicationInstance created
 -> start_application_installation task
 -> child Services/Deploys

GET installation
 -> owner queryset
 -> ApplicationInstanceSerializer
 -> coordinator snapshot only

Source: src/app_catalog/serializers.py and apis.py.
