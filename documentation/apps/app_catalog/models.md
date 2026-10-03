# app_catalog models

## ApplicationStatus

The coordinator status choices are:
- pending: installation has been created but child orchestration has not completed.
- deploying: coordinator is actively advancing child services.
- running: all required child services reached the coordinator's successful condition.
- failed: coordinator stopped because a required child failed or orchestration failed.
- cancelled: installation was intentionally cancelled.

The coordinator state is not a Deploy state. Child Deploy records have their own lifecycle.

## ApplicationInstance

The durable owner and coordinator for one catalog installation.

| Field | Type / default | Semantics |
|---|---|---|
| id | UUID primary key | Stable installation identity. |
| user | FK users.User CASCADE | Customer ownership; installation list/detail are owner-scoped. |
| name | CharField(50) | User-facing installation name. Validated at install request. |
| slug | SlugField(50) | Stable identifier for service-name/rendering purposes. |
| catalog_id | CharField(64) | Catalog definition identity selected by the user. |
| definition_version | CharField(32) | Version/provenance of the definition used for this installation. |
| software_version | CharField(64), default unknown | Selected application software release. |
| variant_id | CharField(64) | Exact catalog variant installed. Reconciliation must remain tied to this variant even if the catalog later changes. |
| definition_snapshot | JSON, default {} | Immutable installation intent. `_application_orchestration.services[]` is the sole coordinator graph and contains child key, role, platform, plan type, dependencies and required flag. Recovery never reads mutable Service runtime metadata or reloads a catalog. |
| config | JSON, default {} | Non-secret normalized user configuration used while materializing child Services. It may contain derived non-secret values such as the installation slug. |
| secret_config | JSON, default {} | Compatibility field retained for older API/database rows; new installs intentionally leave it empty. `secrets_configured` is derived from enabled child ServiceSecret keys, while secret values live only in ServiceSecret/ServiceSecretVersion. |
| status | ApplicationStatus, default pending | Coordinator state machine. Written by app_catalog tasks. |
| error_code | CharField(96), blank | Stable machine-oriented failure reason for UI/recovery. |
| error_message | Text, blank | Human-readable failure detail. |
| created_at / updated_at | DateTime | Lifecycle audit. |
| deployed_at | DateTime nullable | Time the coordinator reached its deployed condition. |
| stage | CharField(64), default pending | Fine-grained coordinator progress label, not a replacement for status. |
| execution_task_id | CharField(64), indexed | Current coordinator Celery task ownership/correlation. |
| started_at | DateTime nullable | Coordinator execution start. |
| execution_deadline | DateTime nullable | Deadline used for stale/recovery handling. |
| cancel_requested | Boolean, default false | Cancellation intent; tasks must observe it before dispatching further child work. |
| network | OneToOne services.PrivateNetwork, CASCADE, nullable | Shared private network for the application's child Services. |

## ApplicationInstanceService

Binds one catalog service definition to its concrete Service and Deploy records.

| Field | Type | Semantics |
|---|---|---|
| instance | FK ApplicationInstance, CASCADE | Coordinator ownership. |
| service | OneToOne services.Service, RESTRICT | Concrete child Service created from the catalog plan; the application binding must be removed before the Service can be deleted. |
| deploy | OneToOne deploy.Deploy, PROTECT | Concrete execution/provenance record for that child; deleting the binding must not silently delete the deployment record. |
| service_key | CharField(64) | Stable definition key used to map catalog intent to the child resource. Unique within the installation. |
| sequence | PositiveInteger, default 0 | Dispatch order. Coordinator uses it for deterministic one-at-a-time progression. |
| dispatch_task_id | CharField(64), indexed | Child dispatch Celery task ownership/correlation. |
| dispatched_at | DateTime nullable | Records when this child was handed to background execution. |

## JSON contracts

definition_snapshot is a provenance snapshot; it must contain enough resolved definition information to reproduce coordinator decisions without trusting a later catalog revision.

config contains user-facing non-secret inputs after install validation and normalization.

secret_config contains generated credentials or secret substitutions needed by child creation. It is never a normal API response field.

Do not add arbitrary runtime policy into ApplicationInstance.config. Runtime/build ceilings belong to plans/core/deployments.

## Creation, mutation and deletion

ApplicationInstance is created by validate_install_request/create_application_installation. Tasks mutate coordinator status/stage/error/task ownership. Child Service/Deploy rows are created as ordinary domain/runtime records.

DELETE is intentionally restricted to terminal application state and rejects active child deployments before removing children and the application-owned network.

## Architectural invariants

1. Catalog coordinates; deployments executes.
2. Child services use the normal services -> ServiceRevision -> Deploy -> deployments path.
3. Coordinator and child execution state are distinct.
4. Cancellation prevents future child dispatch and attempts safe cleanup of existing children.
5. The stored variant/definition snapshot is required for deterministic recovery.
