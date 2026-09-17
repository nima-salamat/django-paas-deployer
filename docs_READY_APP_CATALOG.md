# Ready-to-Deploy Service Catalog

PassDeployer's Ready-to-Deploy catalog is a repository-backed declarative layer above the deployment engine.

## Sources

Bundled definitions live under `app_catalog/catalog/`. Additional repositories/directories can be mounted through the `APP_CATALOG_SOURCE_DIRS` environment variable. Every `*.yml`/`*.yaml` file in those directories is treated as an import candidate and is validated before it is exposed as a catalog entry.

This allows a checked-out external catalog such as a Coolify-style `templates/compose` directory to be imported without changing deployment-engine code.

## Definition flow

```text
Compose/template source
    -> catalog metadata + variable inference
    -> security validation
    -> resolved configuration/secrets
    -> ApplicationPlan
    -> ApplicationStackExecutor
    -> existing Service/Deploy engine
```

Compose is an input format, not an execution engine. Unsupported Compose semantics are rejected rather than silently translated.

## Supported generic concepts

A catalog definition can describe:

- one or many services;
- prebuilt images or Dockerfile builds;
- application-specific metadata and tags;
- dynamic configuration fields;
- generated secrets;
- service dependencies and health/readiness checks;
- persistent named volumes;
- public versus internal services;
- commands and working directories;
- environment interpolation and service-host references;
- application definition version versus software/image version.

The deployment engine remains application-agnostic.

## Variable/import conventions

The importer understands both PassDeployer placeholders such as `${config.domain}` and `${secret.password}` and common Coolify-style variables such as:

- `SERVICE_URL_<SERVICE>_<PORT>`
- `SERVICE_FQDN_<SERVICE>`
- `SERVICE_USER_<SERVICE>`
- `SERVICE_PASSWORD_<SERVICE>`
- `${NAME:-default}` / `${NAME:?required}`

Generated secret variables become per-installation secret fields rather than catalog-stored secrets.

`$${...}` is preserved as a container-runtime expansion after catalog interpolation, which is required by templates that intentionally defer variables to the container environment.

## Security boundary

Catalog import rejects, among other things:

- privileged mode;
- host networking;
- Docker runtime/device/capability escape mechanisms;
- host bind mounts;
- top-level Compose `secrets`/`configs` objects;
- service `container_name`/`restart`/host-DNS overrides;
- unsupported network definitions;
- hard-coded sensitive environment values.

These features require explicit future platform support. They must not be silently approximated.

## Representative catalog

The current bundled set intentionally spans different shapes rather than trying to enumerate a full marketplace:

- Uptime Kuma — one public stateful service;
- MinIO — one public stateful storage service;
- PostgreSQL — single internal infrastructure service;
- Redis — single internal cache service;
- Docmost — application + PostgreSQL + Redis;
- Forgejo + PostgreSQL — application + database;
- n8n + PostgreSQL + Redis + worker — application + dependencies + worker;
- Mattermost + PostgreSQL — application + database;
- Synapse + PostgreSQL — application + database.

More applications should normally be added as catalog data or imported repository files, not by editing the deployment engine.

## Versioning

An installed application stores both the catalog definition version and the software/image version. Updating a catalog repository therefore does not silently mutate an existing installation's recorded definition.
