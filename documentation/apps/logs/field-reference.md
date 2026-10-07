# logs — model field reference

This page is a source-derived reference of every Django model field declared in `src/logs/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/logs/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## ServiceLogStream

**Bases:** `models.Model`  
**Declared fields:** 17

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `id` | `BigAutoField` | no | no | `—` | DB non-null, blank not allowed | Primary identity of the record. |
| `service_id` | `UUIDField` | no | no | `—` | DB non-null, blank not allowed, indexed | Associates this record with the durable Service it belongs to or targets. |
| `deploy_id` | `UUIDField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Associates the record with a deployment attempt/provenance record. |
| `container_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the container id value required by ServiceLogStream for its CharField contract. |
| `container_name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the container name value required by ServiceLogStream for its CharField contract. |
| `started_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed, indexed | Stores the started at value required by ServiceLogStream for its DateTimeField contract. |
| `ended_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the ended at value required by ServiceLogStream for its DateTimeField contract. |
| `status` | `CharField` | no | no | `Status.ACTIVE` | DB non-null, blank not allowed, indexed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `last_persisted_ts` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last persisted ts value required by ServiceLogStream for its DateTimeField contract. |
| `last_persisted_fingerprint` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the last persisted fingerprint value required by ServiceLogStream for its CharField contract. |
| `last_seq` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the last seq value required by ServiceLogStream for its BigIntegerField contract. |
| `owner_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the owner id value required by ServiceLogStream for its CharField contract. |
| `lease_until` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the lease until value required by ServiceLogStream for its DateTimeField contract. |
| `lease_token` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the lease token value required by ServiceLogStream for its CharField contract. |
| `heartbeat_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the heartbeat at value required by ServiceLogStream for its DateTimeField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `id`: `BigAutoField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `service_id`: `UUIDField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `deploy_id`: `UUIDField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `container_id`: `CharField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `container_name`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `started_at`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `ended_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, indexed, choices. The model declaration is authoritative for validation and persistence behavior.
- `last_persisted_ts`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_persisted_fingerprint`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_seq`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `owner_id`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `lease_until`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `lease_token`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `heartbeat_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceLogEntry

**Bases:** `models.Model`  
**Declared fields:** 13

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `id` | `BigAutoField` | no | no | `—` | DB non-null, blank not allowed | Primary identity of the record. |
| `service_id` | `UUIDField` | no | no | `—` | DB non-null, blank not allowed, indexed | Associates this record with the durable Service it belongs to or targets. |
| `stream_id` | `BigIntegerField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the stream id value required by ServiceLogEntry for its BigIntegerField contract. |
| `deploy_id` | `UUIDField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `ts` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the ts value required by ServiceLogEntry for its DateTimeField contract. |
| `seq` | `BigIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the seq value required by ServiceLogEntry for its BigIntegerField contract. |
| `stream` | `CharField` | no | no | `StreamKind.STDOUT` | DB non-null, blank not allowed, choices | Stores the stream value required by ServiceLogEntry for its CharField contract. |
| `level` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the level value required by ServiceLogEntry for its CharField contract. |
| `message` | `TextField` | no | no | `—` | DB non-null, blank not allowed | Associates the record with a message or message history. |
| `byte_size` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the byte size value required by ServiceLogEntry for its PositiveIntegerField contract. |
| `truncated` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the truncated value required by ServiceLogEntry for its BooleanField contract. |
| `fingerprint` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the fingerprint value required by ServiceLogEntry for its CharField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |

### Field-level notes

- `id`: `BigAutoField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `service_id`: `UUIDField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `stream_id`: `BigIntegerField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `deploy_id`: `UUIDField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `ts`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `seq`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `stream`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `level`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `message`: `TextField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `byte_size`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `truncated`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `fingerprint`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceLogUsage

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service_id` | `UUIDField` | no | no | `—` | DB non-null, blank not allowed | Associates this record with the durable Service it belongs to or targets. |
| `current_storage_bytes` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the current storage bytes value required by ServiceLogUsage for its BigIntegerField contract. |
| `entry_count` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the entry count value required by ServiceLogUsage for its BigIntegerField contract. |
| `entries_dropped` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the entries dropped value required by ServiceLogUsage for its BigIntegerField contract. |
| `bytes_dropped` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the bytes dropped value required by ServiceLogUsage for its BigIntegerField contract. |
| `last_ingestion_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last ingestion at value required by ServiceLogUsage for its DateTimeField contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `service_id`: `UUIDField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `current_storage_bytes`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `entry_count`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `entries_dropped`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `bytes_dropped`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_ingestion_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## LogUsageDaily

**Bases:** `models.Model`  
**Declared fields:** 9

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `id` | `BigAutoField` | no | no | `—` | DB non-null, blank not allowed | Primary identity of the record. |
| `service_id` | `UUIDField` | no | no | `—` | DB non-null, blank not allowed, indexed | Associates this record with the durable Service it belongs to or targets. |
| `date` | `DateField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the date value required by LogUsageDaily for its DateField contract. |
| `bytes_ingested` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the bytes ingested value required by LogUsageDaily for its BigIntegerField contract. |
| `entries_ingested` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the entries ingested value required by LogUsageDaily for its BigIntegerField contract. |
| `bytes_deleted` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the bytes deleted value required by LogUsageDaily for its BigIntegerField contract. |
| `entries_deleted` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the entries deleted value required by LogUsageDaily for its BigIntegerField contract. |
| `entries_dropped` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the entries dropped value required by LogUsageDaily for its BigIntegerField contract. |
| `bytes_dropped` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the bytes dropped value required by LogUsageDaily for its BigIntegerField contract. |

### Field-level notes

- `id`: `BigAutoField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `service_id`: `UUIDField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `date`: `DateField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `bytes_ingested`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `entries_ingested`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `bytes_deleted`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `entries_deleted`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `entries_dropped`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `bytes_dropped`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## CollectorHeartbeat

**Bases:** `models.Model`  
**Declared fields:** 15

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `id` | `BigAutoField` | no | no | `—` | DB non-null, blank not allowed | Primary identity of the record. |
| `instance_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Stores the instance id value required by CollectorHeartbeat for its CharField contract. |
| `status` | `CharField` | no | no | `"healthy"` | DB non-null, blank not allowed | Lifecycle/status discriminator used to decide which operations are legal. |
| `last_heartbeat` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Stores the last heartbeat value required by CollectorHeartbeat for its DateTimeField contract. |
| `last_successful_ingestion` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last successful ingestion value required by CollectorHeartbeat for its DateTimeField contract. |
| `active_streams` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the active streams value required by CollectorHeartbeat for its PositiveIntegerField contract. |
| `active_containers` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the active containers value required by CollectorHeartbeat for its PositiveIntegerField contract. |
| `buffer_bytes` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the buffer bytes value required by CollectorHeartbeat for its BigIntegerField contract. |
| `dropped_entries` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the dropped entries value required by CollectorHeartbeat for its BigIntegerField contract. |
| `dropped_bytes` | `BigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the dropped bytes value required by CollectorHeartbeat for its BigIntegerField contract. |
| `last_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the last error value required by CollectorHeartbeat for its TextField contract. |
| `db_ok` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the db ok value required by CollectorHeartbeat for its BooleanField contract. |
| `redis_ok` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the redis ok value required by CollectorHeartbeat for its BooleanField contract. |
| `meta` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the meta value required by CollectorHeartbeat for its JSONField contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `id`: `BigAutoField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `instance_id`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_heartbeat`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_successful_ingestion`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `active_streams`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `active_containers`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `buffer_bytes`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `dropped_entries`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `dropped_bytes`: `BigIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `db_ok`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `redis_ok`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `meta`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
