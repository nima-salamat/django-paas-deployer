# deploy — model field reference

This page is a source-derived reference of every Django model field declared in `src/deploy/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/deploy/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## Deploy

**Bases:** `BaseModel`  
**Declared fields:** 43

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `revision` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=deployments; on_delete=SET_NULL | Stores the revision value required by Deploy for its ForeignKey contract. |
| `created_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=created_deploys; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `version` | `DecimalField` | no | no | `0.00` | DB non-null, blank not allowed | Stores the version value required by Deploy for its DecimalField contract. |
| `release_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stores the release id value required by Deploy for its UUIDField contract. |
| `source_revision` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the source revision value required by Deploy for its CharField contract. |
| `image_ref` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image ref value required by Deploy for its CharField contract. |
| `image_digest` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image digest value required by Deploy for its CharField contract. |
| `runtime_revision_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the runtime revision id value required by Deploy for its CharField contract. |
| `runtime_spec` | `JSONField` | yes | yes | `—` | DB nullable, blank allowed | Stores the runtime spec value required by Deploy for its JSONField contract. |
| `runtime_spec_sha256` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the runtime spec sha256 value required by Deploy for its CharField contract. |
| `cleanup_status` | `CharField` | no | no | `CleanupStatusChoices.NOT_REQUIRED` | DB non-null, blank not allowed, choices | Stores the cleanup status value required by Deploy for its CharField contract. |
| `cleanup_failures` | `JSONField` | no | yes | `list` | DB non-null, blank allowed | Stores the cleanup failures value required by Deploy for its JSONField contract. |
| `reconciliation_required` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed, indexed | Stores the reconciliation required value required by Deploy for its BooleanField contract. |
| `zip_file` | `FileField` | yes | yes | `—` | DB nullable, blank allowed | Stores the zip file value required by Deploy for its FileField contract. |
| `config` | `JSONField` | yes | yes | `—` | DB nullable, blank allowed | User/configuration snapshot used to reproduce the selected behavior. |
| `started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the started at value required by Deploy for its DateTimeField contract. |
| `completed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the completed at value required by Deploy for its DateTimeField contract. |
| `updated_file_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the updated file at value required by Deploy for its DateTimeField contract. |
| `status` | `CharField` | no | no | `DeploymentStatusChoices.PENDING` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `stage` | `CharField` | no | yes | `"idle"` | DB non-null, blank allowed | Stores the stage value required by Deploy for its CharField contract. |
| `base_image_wait_started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the base image wait started at value required by Deploy for its DateTimeField contract. |
| `base_image_ready_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the base image ready at value required by Deploy for its DateTimeField contract. |
| `application_started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the application started at value required by Deploy for its DateTimeField contract. |
| `progress` | `PositiveSmallIntegerField` | no | no | `0` | DB non-null, blank not allowed | Current lifecycle progress projection. |
| `status_message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a message or message history. |
| `error_message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a message or message history. |
| `rollback_status` | `CharField` | no | no | `RollbackStatusChoices.NOT_REQUIRED` | DB non-null, blank not allowed, choices | Stores the rollback status value required by Deploy for its CharField contract. |
| `health_status` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the health status value required by Deploy for its CharField contract. |
| `container_status` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the container status value required by Deploy for its CharField contract. |
| `image_status` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image status value required by Deploy for its CharField contract. |
| `volume_status` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates or configures persistent storage. |
| `network_status` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with its private/network scope. |
| `cancel_requested` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the cancel requested value required by Deploy for its BooleanField contract. |
| `execution_task_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the execution task id value required by Deploy for its CharField contract. |
| `worker_heartbeat_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the worker heartbeat at value required by Deploy for its DateTimeField contract. |
| `previous_deploy` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=replacement_deployments; on_delete=SET_NULL | Associates the record with a deployment attempt/provenance record. |
| `operation` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the operation value required by Deploy for its CharField contract. |
| `operation_started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the operation started at value required by Deploy for its DateTimeField contract. |
| `operation_resource_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the operation resource id value required by Deploy for its CharField contract. |
| `operation_previous_resource_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the operation previous resource id value required by Deploy for its CharField contract. |
| `recovery_metadata` | `JSONField` | yes | yes | `—` | DB nullable, blank allowed | Stores the recovery metadata value required by Deploy for its JSONField contract. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `revision`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `created_by`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `version`: `DecimalField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `release_id`: `UUIDField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `source_revision`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `image_ref`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_digest`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_revision_id`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_spec`: `JSONField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_spec_sha256`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cleanup_status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `cleanup_failures`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `reconciliation_required`: `BooleanField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `zip_file`: `FileField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `config`: `JSONField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `completed_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_file_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `stage`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `base_image_wait_started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `base_image_ready_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `application_started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `progress`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `status_message`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `error_message`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `rollback_status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `health_status`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `container_status`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_status`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `volume_status`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `network_status`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cancel_requested`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `execution_task_id`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `worker_heartbeat_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `previous_deploy`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `operation`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `operation_started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `operation_resource_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `operation_previous_resource_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `recovery_metadata`: `JSONField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## DeploymentResource

**Bases:** `BaseModel`  
**Declared fields:** 9

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `deployment` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=resources; on_delete=CASCADE | Associates the record with a deployment attempt/provenance record. |
| `kind` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the kind value required by DeploymentResource for its CharField contract. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `runtime_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the runtime id value required by DeploymentResource for its CharField contract. |
| `state` | `CharField` | no | no | `DeploymentResourceStateChoices.PLANNED` | DB non-null, blank not allowed, choices | Internal lifecycle/state-machine discriminator. |
| `owned` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the owned value required by DeploymentResource for its BooleanField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by DeploymentResource for its TextField contract. |
| `retired_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the retired at value required by DeploymentResource for its DateTimeField contract. |

### Field-level notes

- `deployment`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `kind`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `state`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `owned`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `retired_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## DeploymentEventOutbox

**Bases:** `BaseModel`  
**Declared fields:** 12

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `event_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stores the event id value required by DeploymentEventOutbox for its UUIDField contract. |
| `deployment` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=event_outbox; on_delete=CASCADE | Associates the record with a deployment attempt/provenance record. |
| `service_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Associates this record with the durable Service it belongs to or targets. |
| `event_type` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the event type value required by DeploymentEventOutbox for its CharField contract. |
| `stage` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the stage value required by DeploymentEventOutbox for its CharField contract. |
| `level` | `CharField` | no | no | `"info"` | DB non-null, blank not allowed | Stores the level value required by DeploymentEventOutbox for its CharField contract. |
| `occurred_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed, indexed | Stores the occurred at value required by DeploymentEventOutbox for its DateTimeField contract. |
| `payload` | `JSONField` | no | no | `dict` | DB non-null, blank not allowed | Stores the payload value required by DeploymentEventOutbox for its JSONField contract. |
| `dispatched_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the dispatched at value required by DeploymentEventOutbox for its DateTimeField contract. |
| `next_attempt_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the next attempt at value required by DeploymentEventOutbox for its DateTimeField contract. |
| `attempts` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the attempts value required by DeploymentEventOutbox for its PositiveIntegerField contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by DeploymentEventOutbox for its TextField contract. |

### Field-level notes

- `event_id`: `UUIDField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `deployment`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service_id`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `event_type`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `stage`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `level`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `occurred_at`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `payload`: `JSONField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `dispatched_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `next_attempt_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `attempts`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## DeployLog

**Bases:** `BaseModel`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `event_id` | `UUIDField` | yes | yes | `—` | DB nullable, blank allowed, unique, indexed | Stores the event id value required by DeployLog for its UUIDField contract. |
| `deploy` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=+; on_delete=DO_NOTHING | Associates the record with a deployment attempt/provenance record. |
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=+; on_delete=DO_NOTHING | Associates this record with the durable Service it belongs to or targets. |
| `stage` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the stage value required by DeployLog for its CharField contract. |
| `event_type` | `CharField` | no | no | `"deployment.event"` | DB non-null, blank not allowed | Stores the event type value required by DeployLog for its CharField contract. |
| `level` | `CharField` | no | no | `"info"` | DB non-null, blank not allowed | Stores the level value required by DeployLog for its CharField contract. |
| `message` | `TextField` | no | no | `—` | DB non-null, blank not allowed | Associates the record with a message or message history. |
| `progress` | `PositiveSmallIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Current lifecycle progress projection. |
| `details` | `JSONField` | yes | yes | `—` | DB nullable, blank allowed | Stores the details value required by DeployLog for its JSONField contract. |
| `exception_type` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the exception type value required by DeployLog for its CharField contract. |
| `traceback` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the traceback value required by DeployLog for its TextField contract. |

### Field-level notes

- `event_id`: `UUIDField` with DB nullable, blank allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `deploy`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `stage`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `event_type`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `level`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `message`: `TextField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `progress`: `PositiveSmallIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `details`: `JSONField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `exception_type`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `traceback`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## BuildCacheArtifact

**Bases:** `BaseModel`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `deployment` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=cache_artifact; on_delete=CASCADE | Associates the record with a deployment attempt/provenance record. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=build_cache_artifacts; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=build_cache_artifacts; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `image_ref` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the image ref value required by BuildCacheArtifact for its CharField contract. |
| `image_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the image id value required by BuildCacheArtifact for its CharField contract. |
| `image_digest` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image digest value required by BuildCacheArtifact for its CharField contract. |
| `size_bytes` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the size bytes value required by BuildCacheArtifact for its BigIntegerField contract. |
| `last_used_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed, indexed | Most recent use timestamp for access/reconciliation/cleanup decisions. |
| `pinned` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the pinned value required by BuildCacheArtifact for its BooleanField contract. |
| `reclaimed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the reclaimed at value required by BuildCacheArtifact for its DateTimeField contract. |
| `reclaim_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the reclaim error value required by BuildCacheArtifact for its TextField contract. |

### Field-level notes

- `deployment`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `image_ref`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_id`: `CharField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `image_digest`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `size_bytes`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_used_at`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `pinned`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `reclaimed_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `reclaim_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## BuildCacheQuota

**Bases:** `BaseModel`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `quota_mb` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the quota mb value required by BuildCacheQuota for its PositiveIntegerField contract. |
| `retention_days` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the retention days value required by BuildCacheQuota for its PositiveIntegerField contract. |
| `keep_successful_deployments` | `PositiveSmallIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `user` | `OneToOneField` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=build_cache_quota; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `service` | `OneToOneField` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=build_cache_quota; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |

### Field-level notes

- `quota_mb`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `retention_days`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `keep_successful_deployments`: `PositiveSmallIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `OneToOneField` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service`: `OneToOneField` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.

## BaseRuntimeImageLease

**Bases:** `BaseModel`  
**Declared fields:** 4

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `base_image` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=leases; on_delete=CASCADE | Stores the base image value required by BaseRuntimeImageLease for its ForeignKey contract. |
| `deployment_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Associates the record with a deployment attempt/provenance record. |
| `acquired_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Stores the acquired at value required by BaseRuntimeImageLease for its DateTimeField contract. |
| `released_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the released at value required by BaseRuntimeImageLease for its DateTimeField contract. |

### Field-level notes

- `base_image`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `deployment_id`: `CharField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `acquired_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `released_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## BaseRuntimeImage

**Bases:** `BaseModel`  
**Declared fields:** 24

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `logical_runtime` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the logical runtime value required by BaseRuntimeImage for its CharField contract. |
| `runtime_version` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the runtime version value required by BaseRuntimeImage for its CharField contract. |
| `variant` | `CharField` | no | no | `"default"` | DB non-null, blank not allowed | Stores the variant value required by BaseRuntimeImage for its CharField contract. |
| `architecture` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the architecture value required by BaseRuntimeImage for its CharField contract. |
| `docker_host` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the docker host value required by BaseRuntimeImage for its CharField contract. |
| `source_image` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the source image value required by BaseRuntimeImage for its CharField contract. |
| `image_repository` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the image repository value required by BaseRuntimeImage for its CharField contract. |
| `image_tag` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the image tag value required by BaseRuntimeImage for its CharField contract. |
| `image_ref` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the image ref value required by BaseRuntimeImage for its CharField contract. |
| `image_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image id value required by BaseRuntimeImage for its CharField contract. |
| `image_digest` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the image digest value required by BaseRuntimeImage for its CharField contract. |
| `status` | `CharField` | no | no | `Status.PENDING` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `auto_build` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the auto build value required by BaseRuntimeImage for its BooleanField contract. |
| `rebuild_requested` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the rebuild requested value required by BaseRuntimeImage for its BooleanField contract. |
| `rebuild_requested_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the rebuild requested at value required by BaseRuntimeImage for its DateTimeField contract. |
| `build_started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the build started at value required by BaseRuntimeImage for its DateTimeField contract. |
| `build_completed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the build completed at value required by BaseRuntimeImage for its DateTimeField contract. |
| `build_count` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the build count value required by BaseRuntimeImage for its PositiveIntegerField contract. |
| `build_task_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the build task id value required by BaseRuntimeImage for its CharField contract. |
| `build_owner_deployment_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `definition_fingerprint` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the definition fingerprint value required by BaseRuntimeImage for its CharField contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by BaseRuntimeImage for its TextField contract. |
| `last_error_details` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the last error details value required by BaseRuntimeImage for its JSONField contract. |

### Field-level notes

- `logical_runtime`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_version`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `variant`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `architecture`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `docker_host`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `source_image`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_repository`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_tag`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_ref`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `image_digest`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `auto_build`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `rebuild_requested`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `rebuild_requested_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_completed_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_count`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_task_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_owner_deployment_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `definition_fingerprint`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error_details`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## SwarmCluster

**Bases:** `BaseModel`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `"default"` | DB non-null, blank not allowed, unique | Human-readable or user-selected name used for identification and UI. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `manager_endpoint` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the manager endpoint value required by SwarmCluster for its CharField contract. |
| `last_synced_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last synced at value required by SwarmCluster for its DateTimeField contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by SwarmCluster for its TextField contract. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `manager_endpoint`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_synced_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## SwarmNode

**Bases:** `BaseModel`  
**Declared fields:** 15

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `cluster` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=nodes; on_delete=CASCADE | Stores the cluster value required by SwarmNode for its ForeignKey contract. |
| `docker_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Stores the docker id value required by SwarmNode for its CharField contract. |
| `hostname` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the hostname value required by SwarmNode for its CharField contract. |
| `role` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the role value required by SwarmNode for its CharField contract. |
| `desired_availability` | `CharField` | no | no | `Availability.ACTIVE` | DB non-null, blank not allowed, choices | Stores the desired availability value required by SwarmNode for its CharField contract. |
| `observed_availability` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the observed availability value required by SwarmNode for its CharField contract. |
| `observed_state` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the observed state value required by SwarmNode for its CharField contract. |
| `address` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the address value required by SwarmNode for its CharField contract. |
| `labels` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the labels value required by SwarmNode for its JSONField contract. |
| `desired_labels` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the desired labels value required by SwarmNode for its JSONField contract. |
| `cpus` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the cpus value required by SwarmNode for its PositiveIntegerField contract. |
| `memory_bytes` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the memory bytes value required by SwarmNode for its BigIntegerField contract. |
| `manager_reachable` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the manager reachable value required by SwarmNode for its BooleanField contract. |
| `last_synced_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last synced at value required by SwarmNode for its DateTimeField contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by SwarmNode for its TextField contract. |

### Field-level notes

- `cluster`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `docker_id`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `hostname`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `role`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `desired_availability`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `observed_availability`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `observed_state`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `address`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `labels`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `desired_labels`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cpus`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `memory_bytes`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `manager_reachable`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_synced_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
