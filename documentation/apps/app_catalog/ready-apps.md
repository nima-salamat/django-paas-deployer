# Ready Apps

Ready Apps are the curated, user-facing application experience built on top of the existing `app_catalog` installation coordinator and the normal Service/Deploy deployment pipeline.

This document is the canonical engineering and product-contract reference for the Ready Apps feature.

## Scope

The public flow is:

```text
Catalog source
  -> curated/public definition
  -> safe catalog DTO
  -> user configuration
  -> server-side resolution
  -> server-authoritative resource preview
  -> ApplicationInstance
  -> child Service + Deploy records
  -> existing deployments engine
  -> Docker/Swarm
  -> installation status/workspace
```

Ready Apps do not introduce a second runtime, a tenant-facing arbitrary Compose importer, a second deployment engine, a new resource-policy system, a new secret store, or a custom-domain ownership workflow.

## Publication boundary

A definition is eligible for the public Ready Apps API only when both conditions are true:

1. `visibility` is `public`.
2. The definition source is directly under `src/app_catalog/catalog/first_party/`.

This is implemented by the shared `is_public_definition()` policy. There is intentionally no application-id denylist.

A definition can remain installed in the catalog while being internal, experimental, externally supplied, deprecated, or otherwise unavailable to the public product.

## Catalog authoring contract

Compose YAML is the trusted authoring representation for the current first-party Ready App recipes.

The loader reads product metadata from the YAML `x-passdeployer` section and combines it with the Compose document.

Supported product metadata includes:

| Metadata | Purpose |
|---|---|
| `id` | Stable catalog identifier used by APIs and installations |
| `name` | Human-readable product name |
| `version` / `software_version` | Software release displayed to users and persisted for provenance |
| `definition_version` | Version of the PassDeployer catalog definition contract |
| `visibility` | Publication policy; use `public` for Ready Apps |
| `featured` | Frontend ordering/highlight hint |
| `features` | Product capability labels |
| `requirements` | Human-readable deployment prerequisites |
| `outputs` | Safe result/output labels such as `url` |
| `managed_components` | Safe component labels and optional roles |
| `links` | Documentation, website, repository or support links |
| `fields` | User-facing configuration schema |

The source loader also supports header metadata such as `documentation`, `slogan`, `category`, `tags`, `logo`, and `port`.

### Field schema

A variant field can use one of:

- `string`
- `integer`
- `boolean`
- `choice`
- `domain`
- `secret`

Common UI metadata:

```yaml
fields:
  - id: example
    label: Example
    type: string
    required: true
    user_editable: true
    default: value
    ui:
      group: general
      order: 10
      advanced: false
      placeholder: Enter a value
    visible_when:
      field: another_field
      equals: enabled
```

Choice fields require `options`.

A field with `user_editable: false` is an internal/platform field. It can be used by the resolver but is removed from the public DTO.

Secret fields use `type: secret` or `secret: true`. Generated secrets are resolved server-side and are never exposed as plaintext through the public serializers.

## Variants

Each definition has one or more variants. The current Ready Apps UI renders variants from this generic schema; it does not contain per-application wizard code.

Each variant has:

- stable variant id;
- display label;
- availability state;
- optional unavailability reason;
- validated fields;
- service topology.

Only variants with `availability=supported` can be resolved.

## Server-side resolution

The frontend never calculates the executable topology.

`POST /api/application-catalog/apps/<catalog_id>/resolve/`:

1. loads the catalog definition;
2. rejects non-public definitions;
3. validates name, variant and config shape;
4. resolves defaults and generated values;
5. applies platform-owned host configuration;
6. validates the selected Docker APP/READY plan;
7. finds the required database plan for database child services;
8. validates resource/storage limits;
9. returns a safe preview.

The preview and installation therefore share the same backend policy rather than duplicating business rules in React.

## Public API

Authentication is required on all catalog endpoints and uses the existing session-bound JWT path.

### List

`GET /api/application-catalog/apps/`

Returns only the safe public catalog projection. It exposes product metadata, supported variants, editable fields, managed component labels, requirements, outputs and public links.

It does not expose raw Compose data, image wiring, environment-variable templates, internal service keys or secret values.

### Detail

`GET /api/application-catalog/apps/<catalog_id>/`

Returns one safe public application. Internal or non-public definitions behave as not found rather than being disclosed.

### Resolve

`POST /api/application-catalog/apps/<catalog_id>/resolve/`

Request:

```json
{
  "name": "my-wordpress",
  "plan_id": "<uuid>",
  "variant": "default",
  "config": {}
}
```

The response contains:

- `valid`;
- application provenance;
- normalized safe `config`;
- `generated_fields`;
- `managed_components`;
- `resource_summary`;
- `public_endpoints`;
- `outputs`;
- `warnings`.

Secret plaintext is never returned.

The resource summary includes aggregate CPU/RAM/storage and per-service allocation. Its aggregate contract includes `service_count`, `volume_count`, `storage_mb`, `cpu_vcpu`, `ram_mb`, `hourly_price` and `allocation_kind=plan_limits`.

For current recipes, an omitted catalog volume size resolves to 1024 MB. This is a backend rule and must not be recalculated in the browser.

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

The endpoint repeats definition, variant, resource and hostname validation. Resolve is a preview, not a trust boundary.

Successful creation returns HTTP 202 and a durable `ApplicationInstance`. The coordinator creates ordinary child `Service` and `Deploy` rows. Child Services start in `queued` state so the normal deployment worker can acquire them; child Deploys start `pending`. The existing deployments engine performs build, runtime, readiness, activation, rollback and cleanup.

### Installation detail

`GET /api/application-catalog/installations/<uuid>/`

Installation records are owner-scoped.

The response includes catalog/software provenance, coordinator status/stage, non-secret config, `secrets_configured`, errors, timestamps, managed child service summaries, the application URL only after the installation is `running`, and resource allocation.

A child summary includes catalog service key, concrete Service id/name, Deploy id, Deploy status/stage and safe status/error messages.

### Cancel

`POST /api/application-catalog/installations/<uuid>/cancel/`

Cancellation is available only for non-terminal installations. The endpoint records cancellation intent under a row lock and delegates to the existing application coordinator. If Celery delivery fails, the established synchronous cancellation path is used.

### Delete
Cancellation cleanup is idempotent and recoverable. After all child Deploys reach terminal states, the coordinator removes the managed child Services through the normal Service deletion boundary, which owns runtime/container/image/volume/log cleanup, then removes the application-owned network. The `ApplicationInstance` is retained as cancellation history until explicitly deleted.

The owner-scoped DELETE endpoint is also self-healing for cancelled installations: if asynchronous cleanup was missed, deletion performs the same cleanup synchronously before removing the parent record.
 

`DELETE /api/application-catalog/installations/<uuid>/`

Deletion requires owner scope, a terminal application state (`running`, `failed`, or `cancelled`), and no active child deployment.

Child Services are removed before the application-owned network so attached Docker resources are released safely.

The Ready Apps MVP UI does not expose arbitrary destructive deletion controls, but the lifecycle API documents the supported owner-scoped operation.

## HTTP/error contract

| Condition | Status | Code/behavior |
|---|---:|---|
| Unknown/internal catalog application | 404 | `Catalog application not found.` |
| Invalid configuration/variant | 400 | `error` message |
| Same owner + same application name | 409 | `application_name_conflict` and `existing_installation_id` when available |
| Installation worker cannot be queued | 503 | `APPLICATION_TASK_QUEUE_FAILED`; installation remains durable/pending |
| Cancel on terminal installation | 409 | serialized current installation |
| Delete before terminal | 409 | `application_not_terminal` |
| Delete with active child deployment | 409 | `application_children_active` |

The frontend uses `existing_installation_id` to recover a duplicate-name request by opening the existing installation.

## Hostname and domain policy

Ready Apps currently expose only platform-owned HTTPS hostnames:

```text
<application-slug>.<DEPLOYMENT_DOMAIN>
```

A public definition must declare a `domain` field, but it must be `user_editable: false`.

The resolver computes the deterministic hostname during planning so endpoint/routing configuration can be compiled before containers exist. That hostname is not exposed as a live `application_url` until the installation reaches `running`.

A client-supplied custom `domain` is not accepted by the public Ready Apps API. The resolver forces HTTPS for public Ready App output.

The restriction exists because the platform does not yet implement domain ownership verification.

## Deployment selection and activation

A newly-created Ready App child `Deploy` is intentionally **not** written into `Service.selected_deploy`. The runtime authority is the immutable `ServiceRevision` activated by the deployment engine. `selected_deploy` is a compatibility projection written when activation succeeds.

Therefore the execution prerequisite is:

```text
Service QUEUED + Deploy PENDING
  -> deployment worker
  -> Service DEPLOYING + Deploy RUNNING
  -> runtime readiness
  -> ServiceRevision ACTIVE
  -> Service.selected_deploy projection
```

Database child services are dispatched directly to the dedicated database deployment task so application-level success/failure callbacks remain attached to the actual execution task.
 
## Secrets

Ready Apps use the existing `ServiceSecret`/`ServiceSecretVersion` infrastructure:

```text
user secret or generated value
  -> server-side resolution
  -> child Service secret/version
  -> runtime environment binding
```

New installs intentionally keep `ApplicationInstance.secret_config` empty for sensitive material. The public installation serializer exposes only configured secret-slot names.

Do not place passwords, tokens or generated credentials in normal catalog DTOs or review payloads.

## Resource allocation

The selected Docker APP/READY plan is reused for application-role child services.

Database-role services select the configured DB plan matching their declared database platform.

Preview values describe plan limits, not current runtime usage:

- CPU -> plan `max_cpu`;
- RAM -> plan `max_ram`;
- storage -> declared catalog volume sizes;
- hourly price -> aggregate selected child-plan price.

Each service's storage is checked against its assigned plan allowance.

## Managed service naming

Concrete Service rows created for a Ready App are named from the user-selected application name and the catalog service key, with the execution platform appended as the final component:

```text
<application-slug>-<service-key>-<platform>
```

For example, an installation named `my-deploy` from the WordPress + MariaDB recipe produces:

```text
my-deploy-wordpress-docker
my-deploy-mariadb-mariadb
```

Service names remain globally unique and are limited to 30 characters. When a name already exists, an ordinal is inserted before the final platform suffix rather than replacing the application identity entirely.
 
## Installation state model

| State | Meaning |
|---|---|
| `pending` | Installation exists; orchestration has not completed |
| `deploying` | Child services are being advanced |
| `running` | Required child services reached the successful condition |
| `failed` | Required child work or orchestration failed |
| `cancelled` | Installation was intentionally cancelled |

`stage` is finer-grained coordinator progress, not a replacement for `status`.

Coordinator state and child Deploy state remain separate.

## Current curated MVP

### WordPress + MariaDB

- Catalog id: `wordpress`
- Software version: `7.1.2`
- Application image: `wordpress:7.1.2-php8.3-apache`
- Database image: `mariadb:11.8.9`
- Persistent data: WordPress files + MariaDB data
- Public output: platform HTTPS URL
- User deployment-time secret input: none

After deployment, the user completes the WordPress setup wizard.

### Uptime Kuma

- Catalog id: `uptime-kuma`
- Software version: `2.5.5`
- Image: `louislam/uptime-kuma:2.5.5`
- Persistent data: Uptime Kuma data
- Public output: platform HTTPS URL
- User deployment-time secret input: none

The current recipe expects local POSIX-compatible persistent storage.

### Grafana + PostgreSQL

- Catalog id: `grafana`
- Software version: `13.2.3`
- Application image: `grafana/grafana-oss:13.2.3`
- Database image: `postgres:16.15`
- Persistent data: Grafana + PostgreSQL
- User deployment-time secret: Grafana admin password
- PostgreSQL credentials: generated/platform-managed
- Public output: platform HTTPS URL

These are repository-pinned versions, not a claim that they are the latest upstream releases.

## Adding a new Ready App

1. Place a trusted recipe under `src/app_catalog/catalog/first_party/<recipe>.yaml`.
2. Pin executable image versions; avoid `latest`.
3. Declare `id`, `name`, `version`, `software_version`, `definition_version`, `visibility`, product metadata and managed components.
4. Expose only legitimate tenant controls. Keep platform-owned/generated values non-editable.
5. Use a non-editable `domain` field for a public web endpoint; do not expose DB/cache services publicly.
6. Add health checks, persistence and dependency relationships.
7. Map each service to a supported plan type; DB services must declare the database platform.
8. Add definition, security, resolve, resource, installation/runtime, failure, cancellation and persistence tests.
9. Update this document when the public contract changes.

Compile success alone is not proof of a working Ready App; test both planning and the coordinator/runtime boundary.

## Security invariants

1. Public publication is both metadata- and source-bound.
2. Public serializers never expose raw Compose or secret material.
3. Tenant input cannot select arbitrary hostnames or privileged/host-escape behavior.
4. Resolve is backend-authoritative.
5. Install repeats validation.
6. Ready App children use the normal Service/Deploy/deployment path.
7. Secret values use the existing secret/version system.
8. Internal catalog entries are not disclosed as public products.
9. Database/cache endpoints are not exposed merely because a source file contains ports.
10. Resource ceilings remain platform-owned.

## Tests and verification

The app_catalog contract suite covers catalog schema/source loading, planning, adversarial inputs, compatibility, Ready App runtime integration, installation hardening and recovery/reconciliation.

When changing Ready Apps, verify both the catalog compiler side and the coordinator/runtime side. For frontend changes also verify the route, dynamic field schema, plan loading, resolve, install, conflict recovery, polling, cancellation and Service Detail links.

## Related documents

- [app_catalog architecture](README.md)
- [app_catalog API](api.md)
- [app_catalog models](models.md)
- [app_catalog serializers](serializers.md)
- [app_catalog tests](tests.md)
- [project architecture](../../architecture.md)
