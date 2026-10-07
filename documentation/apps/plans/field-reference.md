# plans — model field reference

This page is a source-derived reference of every Django model field declared in `src/plans/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/plans/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## Plan

**Bases:** `BaseModel`  
**Declared fields:** 14

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `NameChoices.BRONZE` | DB non-null, blank not allowed, choices | Human-readable or user-selected name used for identification and UI. |
| `platform` | `CharField` | no | no | `—` | DB non-null, blank not allowed, choices | Stores the platform value required by Plan for its CharField contract. |
| `max_cpu` | `FloatField` | no | no | `—` | DB non-null, blank not allowed | Stores the max cpu value required by Plan for its FloatField contract. |
| `max_ram` | `FloatField` | no | no | `—` | DB non-null, blank not allowed | Stores the max ram value required by Plan for its FloatField contract. |
| `max_storage` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the max storage value required by Plan for its PositiveIntegerField contract. |
| `price_per_hour` | `FloatField` | no | no | `0.0` | DB non-null, blank not allowed | Stores the price per hour value required by Plan for its FloatField contract. |
| `storage_type` | `CharField` | no | no | `StorageTypeChoices.HDD` | DB non-null, blank not allowed, choices | Stores the storage type value required by Plan for its CharField contract. |
| `plan_type` | `CharField` | no | no | `PlanTypeChoices.APP` | DB non-null, blank not allowed, choices | Selects the resource/policy envelope used by the record. |
| `log_retention_days` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the log retention days value required by Plan for its PositiveIntegerField contract. |
| `log_storage_mb` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the log storage mb value required by Plan for its PositiveIntegerField contract. |
| `log_ingest_bytes_per_sec` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the log ingest bytes per sec value required by Plan for its PositiveIntegerField contract. |
| `persistent_logging` | `BooleanField` | yes | yes | `—` | DB nullable, blank allowed | Stores the persistent logging value required by Plan for its BooleanField contract. |
| `realtime_logging` | `BooleanField` | yes | yes | `—` | DB nullable, blank allowed | Stores the realtime logging value required by Plan for its BooleanField contract. |
| `log_quota_behavior` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the log quota behavior value required by Plan for its CharField contract. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `platform`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `max_cpu`: `FloatField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `max_ram`: `FloatField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `max_storage`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `price_per_hour`: `FloatField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `storage_type`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `plan_type`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `log_retention_days`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `log_storage_mb`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `log_ingest_bytes_per_sec`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `persistent_logging`: `BooleanField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `realtime_logging`: `BooleanField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `log_quota_behavior`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
