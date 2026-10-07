# Shared inherited model fields

`core.base.BaseModel` is the project-wide abstract model base used by deployment/service/domain models.

## BaseModel

| Field | Type | Declared in | Effective on derived models | Purpose |
|---|---|---|---|---|
| `id` | `UUIDField` | `src/core/base/BaseModel.py` | Every model inheriting `BaseModel` | Stable primary identity independent of database row ordering. |
| `created_at` | `DateTimeField` | `src/core/base/BaseModel.py` | Every model inheriting `BaseModel` | Creation timestamp for ordering and audit history. |
| `updated_at` | `DateTimeField` | `src/core/base/BaseModel.py` | Every model inheriting `BaseModel` | Last mutation timestamp for ordering, cache and reconciliation. |

The app field-reference pages list project-declared fields. For `BaseModel` descendants, the three inherited fields above are also part of the effective database schema.

## User framework inheritance

The effective `users.User` model also inherits framework fields from Django `AbstractBaseUser` and `PermissionsMixin`. Those fields are listed in `documentation/apps/users/field-reference.md`.

## Wagtail inheritance

`cms.HomePage` inherits Wagtail `Page` fields. The project reference identifies that inheritance boundary instead of duplicating the complete framework-owned Page schema.

## Rule

A new model reference should record both locally declared fields and the inherited project/framework base that contributes additional fields.
