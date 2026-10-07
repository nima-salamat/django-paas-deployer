# users — model field reference

This page is a source-derived reference of every Django model field declared in `src/users/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/users/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## PermissionMixin

**Bases:** `models.Model`  
**Declared fields:** 1

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `is_superuser` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is superuser value required by PermissionMixin for its BooleanField contract. |

### Field-level notes

- `is_superuser`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## User

**Bases:** `AbstractBaseUser, PermissionsMixin`  
**Declared fields:** 17

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `uuid` | `CharField` | no | no | `get_uuid` | DB non-null, blank not allowed, unique | Stable public/canonical identity that is independent of database ordering. |
| `username` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Stores the username value required by User for its CharField contract. |
| `first_name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the first name value required by User for its CharField contract. |
| `last_name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the last name value required by User for its CharField contract. |
| `password` | `CharField` | yes | yes | `—` | DB nullable, blank allowed | Credential hash or stored password representation; never treat it as plaintext configuration. |
| `email` | `EmailField` | yes | yes | `—` | DB nullable, blank allowed, unique | Stores the email value required by User for its EmailField contract. |
| `email_verified` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the email verified value required by User for its BooleanField contract. |
| `phone_number_verified` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the phone number verified value required by User for its BooleanField contract. |
| `theme` | `CharField` | no | no | `ThemeChoices.LIGHT` | DB non-null, blank not allowed, choices | Stores the theme value required by User for its CharField contract. |
| `color` | `PositiveSmallIntegerField` | no | no | `get_color` | DB non-null, blank not allowed, choices | Stores the color value required by User for its PositiveSmallIntegerField contract. |
| `birthdate` | `DateField` | yes | yes | `—` | DB nullable, blank allowed | Stores the birthdate value required by User for its DateField contract. |
| `balance` | `DecimalField` | no | no | `0` | DB non-null, blank not allowed | Stores the balance value required by User for its DecimalField contract. |
| `is_staff` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is staff value required by User for its BooleanField contract. |
| `deletion_requested_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the deletion requested at value required by User for its DateTimeField contract. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable flag. |
| `date_joined` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Stores the date joined value required by User for its DateTimeField contract. |
| `national_id` | `CharField` | yes | yes | `—` | DB nullable, blank allowed | Stores the national id value required by User for its CharField contract. |

### Field-level notes

- `uuid`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `username`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `first_name`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_name`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `password`: `CharField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `email`: `EmailField` with DB nullable, blank allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `email_verified`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `phone_number_verified`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `theme`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `color`: `PositiveSmallIntegerField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `birthdate`: `DateField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `balance`: `DecimalField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `is_staff`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `deletion_requested_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `is_active`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `date_joined`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `national_id`: `CharField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Receipt

**Bases:** `models.Model`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=receipts; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `amount` | `DecimalField` | no | no | `—` | DB non-null, blank not allowed | Stores the amount value required by Receipt for its DecimalField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |
| `status` | `CharField` | no | no | `PaymentChoices.NOT_PAYED` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |

### Field-level notes

- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `amount`: `DecimalField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.

## Profile

**Bases:** `models.Model`  
**Declared fields:** 4

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `order` | `IntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the order value required by Profile for its IntegerField contract. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `image` | `ImageField` | no | no | `—` | DB non-null, blank not allowed | Stores the image value required by Profile for its ImageField contract. |
| `created_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |

### Field-level notes

- `order`: `IntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `image`: `ImageField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## Rule

**Bases:** `models.Model`  
**Declared fields:** 3

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `user` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=rule; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |
| `created_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |

### Field-level notes

- `user`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
