# app_catalog API

Root mount: /api/application-catalog/

Authentication: catalog endpoints use SessionJWTAuthentication and IsAuthenticated. Installation resources are filtered to the authenticated owner.

## Catalog discovery

| Method | Route | Implementation | Behavior |
|---|---|---|---|
| GET | /apps/ | CatalogListAPIView | Lists available catalog definitions. Does not create Services or Deploys. |
| GET | /apps/<catalog_id>/ | CatalogDetailAPIView | Returns one catalog definition or not-found. |
| POST | /apps/<catalog_id>/resolve/ | CatalogResolveAPIView | Resolves a requested variant/config into a validated application plan. Validation occurs before persistence/deployment. |

## Installation coordinator

| Method | Route | Implementation | Behavior |
|---|---|---|---|
| GET | /installations/ | ApplicationInstanceListCreateAPIView | Returns only the caller's installations. |
| POST | /installations/ | ApplicationInstanceListCreateAPIView | Validates catalog id, variant, name, plan id and config; creates ApplicationInstance and child-plan metadata, then queues start_application_installation. If broker enqueue fails, the row remains durable PENDING and the API reports queue failure instead of pretending the install started. |
| GET | /installations/<uuid>/ | ApplicationInstanceDetailAPIView | Owner-scoped inspection of coordinator state and child-service summaries. |
| DELETE | /installations/<uuid>/ | ApplicationInstanceDetailAPIView | Allowed only for terminal application state and only when no active child deployment remains. Child Services are removed before the application-owned PrivateNetwork. |
| POST | /installations/<uuid>/cancel/ | ApplicationInstanceCancelAPIView | Locks the coordinator, records cancellation intent and queues cancellation. If broker delivery fails, cancellation falls back to the synchronous cancel path. |

## Serialization

ApplicationInstanceSerializer exposes identity, status/stage, safe config, errors and a service summary. Raw secret_config is deliberately not returned; the config representation adds a sorted secrets_configured list.

## Request-to-side-effect chains

### Installation

POST /installations/
 -> input validation
 -> resolve catalog variant and plan
 -> create ApplicationInstance
 -> transaction commit
 -> queue start_application_installation
 -> coordinator creates ordinary Service/Deploy children
 -> child deployment uses the normal deployments pipeline

### Cancellation

POST /installations/<id>/cancel/
 -> owner check + row lock
 -> cancel_requested=True
 -> transaction commit
 -> cancellation task
 -> stop future child dispatch
 -> safely cancel/clean existing children

## Validation/security

Names are limited to 50 characters. plan_id must resolve to a compatible application/ready plan. Definition rendering recognizes config, secret and service-host substitutions; unsupported privileged/host escape features fail closed.

## Idempotency/concurrency

The coordinator stores execution/dispatch task ids and dispatch timestamps. Reconciliation can recover lost task delivery without blindly duplicating child creation. Child Deploy ownership is independent of coordinator ownership. Concurrent same-name installations are finally serialized by the `(user, slug)` database uniqueness constraint; the losing API request returns HTTP 409. Installation materialization is transactional, so a database failure rolls back the ApplicationInstance, network, child Services, secrets, endpoints, volumes and Deploy rows created by that installation.

## Related tests

test_application_plan.py protects planning shape; test_adversarial_contracts.py protects unsafe catalog inputs; test_compatibility.py and integration/test_ready_app_runtime.py protect compatibility/runtime boundaries.

Source: src/app_catalog/apis.py, services.py, tasks.py, serializers.py, urls.py.
