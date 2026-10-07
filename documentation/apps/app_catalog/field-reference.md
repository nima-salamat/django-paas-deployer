# app_catalog — model field reference

This page is a source-derived reference of every Django model field declared in `src/app_catalog/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/app_catalog/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## ApplicationInstance

**Bases:** `models.Model`  
**Declared fields:** 23

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed | Primary identity of the record. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=application_instances; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `slug` | `SlugField` | no | no | `—` | DB non-null, blank not allowed | URL- and machine-safe identifier derived from the human-facing name. |
| `catalog_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the catalog id value required by ApplicationInstance for its CharField contract. |
| `definition_version` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the definition version value required by ApplicationInstance for its CharField contract. |
| `software_version` | `CharField` | no | no | `"unknown"` | DB non-null, blank not allowed | Stores the software version value required by ApplicationInstance for its CharField contract. |
| `variant_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the variant id value required by ApplicationInstance for its CharField contract. |
| `definition_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the definition snapshot value required by ApplicationInstance for its JSONField contract. |
| `config` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | User/configuration snapshot used to reproduce the selected behavior. |
| `secret_config` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the secret config value required by ApplicationInstance for its JSONField contract. |
| `status` | `CharField` | no | no | `ApplicationStatus.PENDING` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `error_code` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the error code value required by ApplicationInstance for its CharField contract. |
| `error_message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a message or message history. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |
| `deployed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `stage` | `CharField` | no | yes | `"pending"` | DB non-null, blank allowed | Stores the stage value required by ApplicationInstance for its CharField contract. |
| `execution_task_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the execution task id value required by ApplicationInstance for its CharField contract. |
| `started_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the started at value required by ApplicationInstance for its DateTimeField contract. |
| `execution_deadline` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the execution deadline value required by ApplicationInstance for its DateTimeField contract. |
| `cancel_requested` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the cancel requested value required by ApplicationInstance for its BooleanField contract. |
| `network` | `OneToOneField` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=application_instance; on_delete=SET_NULL | Associates the record with its private/network scope. |

### Field-level notes

- `id`: `UUIDField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `slug`: `SlugField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `catalog_id`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `definition_version`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `software_version`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `variant_id`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `definition_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `config`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `secret_config`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `error_code`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `error_message`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `deployed_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `stage`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `execution_task_id`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `started_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `execution_deadline`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cancel_requested`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `network`: `OneToOneField` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.

## ApplicationInstanceService

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `instance` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=services; on_delete=CASCADE | Stores the instance value required by ApplicationInstanceService for its ForeignKey contract. |
| `service` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=application_binding; on_delete=RESTRICT | Associates this record with the durable Service it belongs to or targets. |
| `deploy` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=application_binding; on_delete=RESTRICT | Associates the record with a deployment attempt/provenance record. |
| `service_key` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Associates this record with the durable Service it belongs to or targets. |
| `sequence` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the sequence value required by ApplicationInstanceService for its PositiveIntegerField contract. |
| `dispatch_task_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the dispatch task id value required by ApplicationInstanceService for its CharField contract. |
| `dispatched_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the dispatched at value required by ApplicationInstanceService for its DateTimeField contract. |

### Field-level notes

- `instance`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `deploy`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service_key`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `sequence`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `dispatch_task_id`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `dispatched_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## CatalogPublication

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `catalog_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Stores the catalog id value required by CatalogPublication for its CharField contract. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `featured_override` | `BooleanField` | yes | yes | `—` | DB nullable, blank allowed | Stores the featured override value required by CatalogPublication for its BooleanField contract. |
| `notes` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the notes value required by CatalogPublication for its TextField contract. |
| `updated_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=+; on_delete=SET_NULL | Stores the updated by value required by CatalogPublication for its ForeignKey contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `catalog_id`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: When disabled, hide this curated catalog entry from Ready Apps..
- `featured_override`: `BooleanField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Optional override for the catalog recipe.
- `notes`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_by`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
