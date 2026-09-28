# deploy serializers

## DeploySerializer

The deploy representation includes provenance/state fields and derived recent deployment logs. status/stage/progress/error/health/container/image/volume/network/rollback fields and timestamps are read-only execution state.

Writable identity/configuration fields are constrained by ownership and by revision immutability. When a Deploy already has revision attached, service/version/zip_file/config cannot be changed in place; a new deployment/revision path is required.

create() sanitizes tenant config, locks the Service while allocating a deployment name, then saves the Deploy. Database uniqueness remains the final concurrent-create guard.

## MaskedDBConfigField

Write accepts structured config; read may redact SENSITIVE_CONFIG_KEYS. Raw DB credentials are shown only to the Service owner or a share recipient whose effective permissions include can_view_db_credentials.

Catalog-managed deployment config gets additional recursive redaction for common secret key names and known generated secret values.

The field is sensitive to request user, Service ownership/share policy, platform and catalog binding.

## DeploymentZipField

On read, a stored ZIP becomes an authenticated /deploy/<deploy_id>/download/ URL. It does not expose a public media path.

## DeployLogSerializer

Read-only deployment event record. Fields include stage/event_type/level/message/progress/details/exception_type/traceback/timestamp. It reads from the deployment-log database and failure to access that DB does not make normal Deploy serialization fail.

## Mapping

POST /deploy/ -> DeploySerializer validation/create -> Deploy row -> start/queue path -> deployments.

GET /deploy/<id>/ -> DeploySerializer -> recent DeployLog query -> response.

Source: src/deploy/serializers.py.
