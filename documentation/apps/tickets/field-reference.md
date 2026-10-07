# tickets — complete model field reference

Source-derived from `src/tickets/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## Department

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable name used to identify the record. |
| `slug` | `SlugField` | no | yes | `—` | DB non-null, blank allowed, unique | URL-/machine-safe identifier derived from a name. |
| `description` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable state. |
| `order` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Explicit display/execution ordering. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `name`: `CharField` — declaration: `_("name"), max_length=100`
- `slug`: `SlugField` — declaration: `_("slug"), max_length=120, unique=True, blank=True`
- `description`: `TextField` — declaration: `_("description"), blank=True, default=""`
- `is_active`: `BooleanField` — declaration: `_("active"), default=True`
- `order`: `PositiveIntegerField` — declaration: `_("order"), default=0`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## DepartmentMembership

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=department_memberships; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `department` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=memberships; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `is_manager` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is manager required by the DepartmentMembership contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="department_memberships"`
- `department`: `ForeignKey` — declaration: `Department, on_delete=models.CASCADE, related_name="memberships"`
- `is_manager`: `BooleanField` — declaration: `default=False`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## Ticket

**Bases:** `models.Model`  
**Declared fields:** 13

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `public_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique, indexed | Stable public identifier for API/resource references. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=tickets; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `department` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=tickets; on_delete=PROTECT | Relationship to the owning/target domain object required by this model. |
| `service` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=tickets; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `deploy` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=tickets; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `subject` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the subject required by the Ticket contract. |
| `status` | `CharField` | no | no | `Status.OPEN` | DB non-null, blank not allowed, indexed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `priority` | `CharField` | no | no | `Priority.NORMAL` | DB non-null, blank not allowed, indexed, choices; choices | Stores the priority required by the Ticket contract. |
| `assigned_to` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=assigned_tickets; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |
| `closed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the closed at required by the Ticket contract. |
| `last_message_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Message relationship used for message context/history. |

### Declaration details

- `public_id`: `CharField` — declaration: `max_length=20, unique=True, editable=False, db_index=True`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="tickets"`
- `department`: `ForeignKey` — declaration: `Department, on_delete=models.PROTECT, related_name="tickets"`
- `service`: `ForeignKey` — declaration: `"services.Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets", verbose_name="related service",`
- `deploy`: `ForeignKey` — declaration: `"deploy.Deploy", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets", verbose_name="related deploy",`
- `subject`: `CharField` — declaration: `max_length=255`
- `status`: `CharField` — declaration: `max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True`
- `priority`: `CharField` — declaration: `max_length=10, choices=Priority.choices, default=Priority.NORMAL, db_index=True`
- `assigned_to`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets"`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`
- `closed_at`: `DateTimeField` — declaration: `null=True, blank=True`
- `last_message_at`: `DateTimeField` — declaration: `null=True, blank=True, db_index=True`

## TicketMessage

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `ticket` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=messages; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `author` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; related_name=ticket_messages; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `body` | `TextField` | no | no | `—` | DB non-null, blank not allowed | Primary body/content payload. |
| `is_staff_reply` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is staff reply required by the TicketMessage contract. |
| `seen_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the seen at required by the TicketMessage contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `ticket`: `ForeignKey` — declaration: `Ticket, on_delete=models.CASCADE, related_name="messages"`
- `author`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, related_name="ticket_messages"`
- `body`: `TextField` — declaration: ``
- `is_staff_reply`: `BooleanField` — declaration: `default=False`
- `seen_at`: `DateTimeField` — declaration: `null=True, blank=True, db_index=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True, db_index=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## TicketReadState

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `ticket` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=read_states; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=ticket_read_states; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `last_read_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Stores the last read at required by the TicketReadState contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `ticket`: `ForeignKey` — declaration: `Ticket, on_delete=models.CASCADE, related_name="read_states"`
- `user`: `ForeignKey` — declaration: `User, on_delete=models.CASCADE, related_name="ticket_read_states"`
- `last_read_at`: `DateTimeField` — declaration: `default=timezone.now`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## TicketAttachment

**Bases:** `models.Model`  
**Declared fields:** 8

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `ticket` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=attachments; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `message` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=attachments; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `uploaded_by` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed; related_name=ticket_attachments; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `file` | `FileField` | no | no | `—` | DB non-null, blank not allowed | Stores the file required by the TicketAttachment contract. |
| `original_filename` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the original filename required by the TicketAttachment contract. |
| `content_type` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the content type required by the TicketAttachment contract. |
| `size` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the size required by the TicketAttachment contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `ticket`: `ForeignKey` — declaration: `Ticket, on_delete=models.CASCADE, related_name="attachments"`
- `message`: `ForeignKey` — declaration: `TicketMessage, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments"`
- `uploaded_by`: `ForeignKey` — declaration: `User, on_delete=models.SET_NULL, null=True, related_name="ticket_attachments"`
- `file`: `FileField` — declaration: `upload_to=ticket_attachment_path`
- `original_filename`: `CharField` — declaration: `max_length=255`
- `content_type`: `CharField` — declaration: `max_length=120, blank=True, default=""`
- `size`: `PositiveIntegerField` — declaration: `default=0`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.
