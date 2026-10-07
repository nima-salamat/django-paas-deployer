# custom_emails — complete model field reference

Source-derived from `src/custom_emails/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## EmailTemplate

**Bases:** `models.Model`  
**Declared fields:** 8

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Human-readable name used to identify the record. |
| `subject` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the subject required by the EmailTemplate contract. |
| `body` | `TextField` | no | no | `—` | DB non-null, blank not allowed | Primary body/content payload. |
| `description` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable state. |
| `created_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=created_email_templates; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `name`: `CharField` — declaration: `max_length=120, unique=True`
- `subject`: `CharField` — declaration: `max_length=255`
- `body`: `TextField` — declaration: `help_text="HTML. Variables: {{ user.username }}, {{ user.email }}, {{ site_name }}"`
- `description`: `TextField` — declaration: `blank=True, default=""`
- `is_active`: `BooleanField` — declaration: `default=True`
- `created_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_email_templates"`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## EmailLog

**Bases:** `models.Model`  
**Declared fields:** 13

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `recipient` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=email_logs; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `recipient_email` | `EmailField` | no | no | `—` | DB non-null, blank not allowed | Stores the recipient email required by the EmailLog contract. |
| `template` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=logs; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `subject` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the subject required by the EmailLog contract. |
| `body_preview` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the body preview required by the EmailLog contract. |
| `status` | `CharField` | no | no | `Status.PENDING` | DB non-null, blank not allowed, indexed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `error_message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Diagnostic message retained for failed work. |
| `sent_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=sent_email_logs; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `is_test` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is test required by the EmailLog contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |
| `sent_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the sent at required by the EmailLog contract. |
| `failed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the failed at required by the EmailLog contract. |
| `celery_task_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the celery task id required by the EmailLog contract. |

### Declaration details

- `recipient`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_logs"`
- `recipient_email`: `EmailField` — declaration: ``
- `template`: `ForeignKey` — declaration: `EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"`
- `subject`: `CharField` — declaration: `max_length=255`
- `body_preview`: `TextField` — declaration: `blank=True, default=""`
- `status`: `CharField` — declaration: `max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True`
- `error_message`: `TextField` — declaration: `blank=True, default=""`
- `sent_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_email_logs"`
- `is_test`: `BooleanField` — declaration: `default=False`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`
- `sent_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `failed_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `celery_task_id`: `CharField` — declaration: `max_length=64, blank=True, default=""`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.
