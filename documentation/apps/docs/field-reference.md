# docs — complete model field reference

Source-derived from `src/docs/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## DocumentCategory

**Bases:** `models.Model`  
**Declared fields:** 9

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed | Primary identity of the record. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable name used to identify the record. |
| `slug` | `SlugField` | no | no | `—` | DB non-null, blank not allowed, unique | URL-/machine-safe identifier derived from a name. |
| `parent` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=children; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `description` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `icon` | `CharField` | no | yes | `"folder"` | DB non-null, blank allowed | Stores the icon required by the DocumentCategory contract. |
| `order` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Explicit display/execution ordering. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |

### Declaration details

- `id`: `UUIDField` — declaration: `primary_key=True, default=uuid.uuid4, editable=False`
- `name`: `CharField` — declaration: `max_length=140`
- `slug`: `SlugField` — declaration: `max_length=180, unique=True`
- `parent`: `ForeignKey` — declaration: `"self", null=True, blank=True, related_name="children", on_delete=models.CASCADE`
- `description`: `CharField` — declaration: `max_length=320, blank=True, default=""`
- `icon`: `CharField` — declaration: `max_length=64, blank=True, default="folder"`
- `order`: `PositiveIntegerField` — declaration: `default=0`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`

## Document

**Bases:** `models.Model`  
**Declared fields:** 12

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed | Primary identity of the record. |
| `title` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-facing title. |
| `slug` | `SlugField` | no | no | `—` | DB non-null, blank not allowed, unique | URL-/machine-safe identifier derived from a name. |
| `description` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `category` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=documents; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `icon` | `CharField` | no | yes | `"description"` | DB non-null, blank allowed | Stores the icon required by the Document contract. |
| `order` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Explicit display/execution ordering. |
| `status` | `CharField` | no | no | `Status.DRAFT` | DB non-null, blank not allowed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `content` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the content required by the Document contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |
| `published_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the published at required by the Document contract. |

### Declaration details

- `id`: `UUIDField` — declaration: `primary_key=True, default=uuid.uuid4, editable=False`
- `title`: `CharField` — declaration: `max_length=180`
- `slug`: `SlugField` — declaration: `max_length=220, unique=True`
- `description`: `CharField` — declaration: `max_length=320, blank=True, default=""`
- `category`: `ForeignKey` — declaration: `DocumentCategory, null=True, blank=True, related_name="documents", on_delete=models.SET_NULL`
- `icon`: `CharField` — declaration: `max_length=64, blank=True, default="description"`
- `order`: `PositiveIntegerField` — declaration: `default=0`
- `status`: `CharField` — declaration: `max_length=16, choices=Status.choices, default=Status.DRAFT`
- `content`: `TextField` — declaration: `blank=True, default=""`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`
- `published_at`: `DateTimeField` — declaration: `null=True, blank=True`

## DocumentAsset

**Bases:** `models.Model`  
**Declared fields:** 9

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed | Primary identity of the record. |
| `document` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=assets; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `file` | `FileField` | no | no | `—` | DB non-null, blank not allowed | Stores the file required by the DocumentAsset contract. |
| `name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-readable name used to identify the record. |
| `alt` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the alt required by the DocumentAsset contract. |
| `kind` | `CharField` | no | no | `Kind.FILE` | DB non-null, blank not allowed, choices; choices | Stores the kind required by the DocumentAsset contract. |
| `mime_type` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the mime type required by the DocumentAsset contract. |
| `size_bytes` | `PositiveBigIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the size bytes required by the DocumentAsset contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `id`: `UUIDField` — declaration: `primary_key=True, default=uuid.uuid4, editable=False`
- `document`: `ForeignKey` — declaration: `Document, related_name="assets", null=True, blank=True, on_delete=models.SET_NULL`
- `file`: `FileField` — declaration: `upload_to=document_asset_path`
- `name`: `CharField` — declaration: `max_length=255, blank=True, default=""`
- `alt`: `CharField` — declaration: `max_length=240, blank=True, default=""`
- `kind`: `CharField` — declaration: `max_length=16, choices=Kind.choices, default=Kind.FILE`
- `mime_type`: `CharField` — declaration: `max_length=120, blank=True, default=""`
- `size_bytes`: `PositiveBigIntegerField` — declaration: `default=0`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.
