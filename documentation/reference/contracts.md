# Source contract inventory

This file is the machine-checkable documentation index for first-party models and HTTP API routes.

**Generation rule:** every inventory row has a stable source signature. CI compares source declarations against these tables and fails when a model, declared field, explicit route, router registration, or router action is added/removed without updating this file.

The detailed app documentation remains the narrative contract. This file answers one narrower question: **does the documented contract inventory contain the thing that exists in source?**

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path |
|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|
| `agent` | `src/agent/models.py` | `Agent` | `BaseModel` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `BaseModel` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `BaseModel` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `BaseModel` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `BaseModel` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `models.Model` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `models.Model` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `models.Model` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `models.Model` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `cms` | `src/cms/models.py` | `HomePage` | `Page` | [field reference](../apps/cms/field-reference.md#homepage) |
| `core` | `src/core/models.py` | `SystemSetting` | `models.Model` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `CoreSettings` | `BaseGenericSetting` | [field reference](../apps/core/field-reference.md#coresettings) |
## Inheritance

Project-wide inherited fields are documented separately in [inherited-model-fields.md](inherited-model-fields.md). The field inventory intentionally records fields declared by each concrete/project model source; inherited framework fields are not duplicated once per model.

## Validation

Run:

```bash
python scripts/validate_documentation_contracts.py
```

Use `--check` in CI. Source code is authoritative; this inventory is intentionally strict and should be regenerated whenever routes or model declarations change.
