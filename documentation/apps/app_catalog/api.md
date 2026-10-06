# app_catalog API

Root mount: /api/application-catalog/

Authentication: catalog endpoints use SessionJWTAuthentication and IsAuthenticated. Installation resources are filtered to the authenticated owner.

## Catalog discovery

| Method | Route | Implementation | Behavior |
|---|---|---|---|
| GET | /apps/ | CatalogListAPIView | Lists the safe public Ready Apps projection. Does not create Services or Deploys. |
| GET | /apps/<catalog_id>/ | CatalogDetailAPIView | Returns one public catalog definition or not-found. Internal definitions are deliberately hidden. |
| POST | /apps/<catalog_id>/resolve/ | CatalogResolveAPIView | Resolves a requested supported variant/config into a validated application plan and server-authoritative resource preview. Validation occurs before persistence/deployment. |

## Public Ready Apps contract

The public catalog surface is not a raw Compose API.

A catalog definition is advertised only when `is_public_definition()` returns true: `visibility=public` and the source file is directly under `src/app_catalog/catalog/first_party/`.

Public serializers exclude:

- raw Compose documents;
- Docker image/environment wiring;
- internal service keys;
- secret values;
- non-user-editable field definitions.

Supported public field types are `string`, `integer`, `boolean`, `choice`, `domain`, and `secret`.

Fields with `user_editable=false` can participate in backend resolution but are omitted from the user-facing field schema.

See [ready-apps.md](ready-apps.md) for the full source metadata contract, hostname policy, recipe guidance, frontend integration and extension checklist.

## Resolve request/response

### Request

```json
{
  "name": "my-app",
  "plan_id": "<uuid>",
  "variant": "default",
  "config": {}
}
```

The backend requires non-empty name, plan id and variant, with config represented as an object.

### Resolution behavior

The resolver:

1. loads the public definition;
2. validates the variant and configuration;
3. applies defaults and generated values;
4. applies the platform-managed HTTPS hostname;
5. validates the selected Docker APP/READY plan;
6. selects the configured database plan for database child services;
7. checks per-service and aggregate storage/resource constraints;
8. returns a safe preview.

The response contains application provenance, normalized safe configuration, generated non-secret field information, managed components, resource summary, public endpoints, outputs and warnings. Secret plaintext is never returned.

The resource summary has aggregate and per-service allocation. Aggregate fields include `service_count`, `volume_count`, `storage_mb`, `cpu_vcpu`, `ram_mb`, `hourly_price` and `allocation_kind=plan_limits`.

## Installation coordinator

| Method | Route | Implementation | Behavior |
|---|---|---|---|
| GET | /installations/ | ApplicationInstanceListCreateAPIView | Returns only the caller's installations. |
| POST | /installations/ | ApplicationInstanceListCreateAPIView | Validates catalog id, variant, name, plan id and config; creates ApplicationInstance and child-plan metadata, then queues start_application_installation. If broker enqueue fails, the row remains durable PENDING and the API reports queue failure instead of pretending the install started. |
| GET | /installations/<uuid>/ | ApplicationInstanceDetailAPIView | Owner-scoped inspection of coordinator state and child-service summaries. |
| DELETE | /installations/<uuid>/ | ApplicationInstanceDetailAPIView | Durable deletion is accepted from every application lifecycle state. The deletion coordinator fences/cancels active child work, removes owned runtime resources, waits for child Deploys to become terminal, then removes child Services and the application-owned PrivateNetwork. |
| POST | /installations/<uuid>/cancel/ | ApplicationInstanceCancelAPIView | Locks the coordinator, records cancellation intent and queues cancellation. If broker delivery fails, cancellation falls back to the synchronous cancel path. |

### Install request

```json
{
  "catalog_id": "wordpress",
  "variant": "default",
  "name": "my-wordpress",
  "plan_id": "<uuid>",
  "config": {}
}
```

The install endpoint revalidates the public definition, variant, resources and platform hostname policy. Resolve is therefore a preview contract, not a trust boundary.

Successful installation creation returns HTTP 202.

The coordinator then creates ordinary child Service and Deploy rows; the existing deployments engine performs the actual build/runtime lifecycle.

## Installation status

`GET /installations/<uuid>/` returns:

- application identity and catalog/software provenance;
- coordinator status and stage;
- normalized non-secret config;
- `secrets_configured` keys without values;
- coordinator errors;
- timestamps;
- managed child Service summaries;
- application URL when a public endpoint is ready;
- resource allocation.

Application status is one of `pending`, `deploying`, `running`, `failed`, or `cancelled`.

`stage` is finer-grained progress information.

## Cancellation

`POST /installations/<uuid>/cancel/` is valid only for non-terminal states.

The endpoint row-locks the ApplicationInstance, records `cancel_requested=true`, commits that intent, then queues the cancellation task. If broker delivery fails, the backend invokes the coordinator's synchronous cancel path.

A terminal cancellation/installation returns HTTP 409 rather than applying an invalid transition.

## Deletion

Deletion requires the caller to own the installation and the application to be terminal.

The API rejects deletion while any child Deploy is in `pending`, `running`, or `rolling_back`.

Child Services are deleted before the installation-owned network. This ordering avoids leaving attached Docker resources behind.

## Error contract

| Condition | Status | Code/behavior |
|---|---:|---|
| Unknown or internal catalog definition | 404 | `Catalog application not found.` |
| Invalid request/configuration | 400 | `error` message |
| Same owner/name conflict | 409 | `application_name_conflict`, with `existing_installation_id` when available |
| Worker queue unavailable | 503 | `APPLICATION_TASK_QUEUE_FAILED`; installation remains durable/pending |
| Cancel terminal installation | 409 | serialized current installation |
| Delete before terminal | 409 | `application_not_terminal` |
| Delete with active child deployment | 409 | `application_children_active` |

## Idempotency/concurrency

The coordinator stores execution/dispatch task ids and dispatch timestamps. Reconciliation can recover lost task delivery without blindly duplicating child creation.

Same-owner application names are protected by the database uniqueness constraint on user + slug. The losing request returns HTTP 409 and the existing installation id when it can be recovered.

Installation materialization is transactional, including network, child Services, secrets, endpoints, volumes and Deploy rows.

## Security and secret serialization

`ApplicationInstanceSerializer` does not serialize `secret_config` values. It derives `secrets_configured` from enabled child ServiceSecret keys.

Generated and user-supplied secrets are materialized through the existing ServiceSecret/ServiceSecretVersion infrastructure. They are not returned by catalog detail, resolve, list, install or installation-detail responses.

## Resource policy

The selected Docker APP/READY plan is reused for application-role children. Database-role children select the first configured database plan matching the declared database platform.

A catalog volume without an explicit size resolves to 1024 MB. Storage is checked against the assigned plan limit. The resource preview is therefore authoritative and must not be recreated in client code.

## Source

Primary implementation: `src/app_catalog/apis.py`, `src/app_catalog/serializers.py`, `src/app_catalog/services.py`, `src/app_catalog/catalog.py`, `src/app_catalog/source_loader.py`, `src/app_catalog/tasks.py`, `src/app_catalog/executor.py`, `src/app_catalog/urls.py`.
