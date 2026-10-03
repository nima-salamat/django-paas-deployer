# Ready Apps

Ready Apps are the curated, user-facing application catalog built on top of the existing application catalog and deployment engine.

## Product boundary

Only catalog definitions explicitly marked `visibility: public` and stored under `src/app_catalog/catalog/first_party/` are advertised as Ready Apps.

The Ready Apps API never exposes raw Compose authoring data, Docker images, environment-variable wiring, labels, internal service keys, or secret values.

Compose YAML remains a trusted catalog authoring/import representation. It is not a tenant-provided deployment interface.

## Deployment flow

The control-plane flow is:

`catalog definition -> user configuration -> server-side resolution -> ApplicationPlan -> ApplicationInstance -> ApplicationInstanceService -> Service -> ServiceRevision -> Deploy -> existing deployment engine`

Ready Apps do not introduce a second runtime or deployment engine.

## Public API

### List

`GET /api/application-catalog/apps/`

Returns only the safe public catalog projection.

### Detail

`GET /api/application-catalog/apps/<catalog_id>/`

Returns public product metadata, supported variants, safe user-editable fields, managed component labels, requirements, outputs, and documentation links.

### Resolve

`POST /api/application-catalog/apps/<catalog_id>/resolve/`

Request:

```json
{
  "name": "my-app",
  "plan_id": "<uuid>",
  "variant": "default",
  "config": {}
}
```

The backend applies the platform-managed HTTPS hostname, validates the variant and plan, compiles the immutable application topology, and returns a resource summary for review.

The response never returns secret plaintext.

### Install

`POST /api/application-catalog/installations/`

Request:

```json
{
  "catalog_id": "wordpress",
  "variant": "default",
  "name": "my-wordpress",
  "plan_id": "<uuid>",
  "config": {}
}
```

The API revalidates the catalog definition, plan, resource allocation, and platform hostname policy before materializing child services.

Repeated names are rejected with `code=application_name_conflict` and, when available, `existing_installation_id` so clients can recover the original installation.

### Installation status

`GET /api/application-catalog/installations/<id>/`

The response includes the application state, public URL when available, managed child services, deploy status/stage, and resource allocation.

### Cancel

`POST /api/application-catalog/installations/<id>/cancel/`

Cancellation is delegated to the existing application stack coordinator and child deployment lifecycle.

## Resource allocation

The review payload is server-authoritative. CPU/RAM values describe selected plan limits for all managed child services; storage describes logical persistent-volume allocation.

For the current catalog importer, an omitted volume size resolves to 1024 MB. This is therefore part of the preview rather than a frontend calculation.

Database child services use the existing database-plan selection policy for their declared database platform.

## Hostname policy

MVP Ready Apps use only platform-controlled HTTPS hostnames:

`<application-slug>.<DEPLOYMENT_DOMAIN>`

Arbitrary custom domains are not accepted by the public Ready Apps API because the platform does not yet have a domain-ownership verification system.

## Secrets

Generated database credentials are stored through the existing service secret/version infrastructure and are not copied into `ApplicationInstance` plaintext configuration.

Current MVP user-visible secret policy:

- WordPress: no deployment-time credential reveal.
- Uptime Kuma: no deployment-time credential reveal.
- Grafana: the user supplies the Grafana admin password; PostgreSQL credentials remain platform-managed.

## Curated MVP recipes

- WordPress + MariaDB
- Uptime Kuma
- Grafana + PostgreSQL

Recipes use explicit software/image versions rather than mutable `latest` tags. Actual runtime image identity remains recorded through the existing deployment provenance fields.
