# Source contract inventory

This document is the canonical machine-checkable inventory for first-party models, declared model fields, API routes, and DRF router registrations.

Source code is authoritative. App-level API/model references explain behavior; this file provides stable source signatures so CI can detect documentation drift.

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|
| `agent` | `src/agent/urls.py` | explicit | `v1/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/agent.md` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/auth/exchange` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/auth/me` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/capabilities` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/cancel` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/logs/export` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/logs` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/rebuild` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/redeploy` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/rollback` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/start` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/upload` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/help` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/inspect` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/networks/<uuid:network_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/networks` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/openapi.json` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/<uuid:plan_id>/apply` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/<uuid:plan_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/manage/<uuid:plan_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/manage` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/configuration` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/database-credentials` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/databases` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/endpoints` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/environment` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/logs/export` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/logs` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/metrics` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/networks` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/purge-runtime` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/rebuild` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/restart` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions/<uuid:revision_id>/rollback` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions/<uuid:revision_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/secrets` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/files` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/replace` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions/<uuid:session_id>/close` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions/<uuid:session_id>/commands` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/start` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/status` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/stop` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/tools/<str:tool_name>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/tools` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/from-plan` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/skills/<slug:skill_name>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/skills` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/volumes/<uuid:volume_id>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/volumes` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<root>` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/<str:action>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/audit/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/revoke/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/rotate/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/manifest/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `scopes/` | [app API docs](../apps/agent/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `apps/<str:catalog_id>/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `apps/<str:catalog_id>/resolve/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `apps/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `installations/<uuid:pk>/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `installations/<uuid:pk>/cancel/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `app_catalog` | `src/app_catalog/urls.py` | explicit | `installations/` | [app API docs](../apps/app_catalog/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/admin/auth-codes/<int:pk>/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/admin/auth-codes/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/admin/auth-codes/purge/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/admin/login-settings/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/authentication/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/devices/<uuid:device_id>/sessions/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/devices/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/invite/create/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/invite/deactivate/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/invite/list/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/invite/validate/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/token/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/token/refresh/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/token/refresh` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/token/verify/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/token/verify` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/login/validate/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/password-recovery/confirm/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/password-recovery/request/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/recovery/confirm/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/recovery/request/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/sessions/<str:session_id>/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/sessions/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/sessions/activity/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/sessions/logout-all/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/set-password/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/settings/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/signup/` | [app API docs](../apps/auth_users/api-reference.md) |
| `auth_users` | `src/auth_users/urls.py` | explicit | `api/validateToken/` | [app API docs](../apps/auth_users/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/<str:key>/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/seed/` | [app API docs](../apps/core/api-reference.md) |

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path | Kind |
|---|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|

## Inheritance

See [inherited-model-fields.md](inherited-model-fields.md) for project-wide BaseModel fields and framework/Wagtail inheritance boundaries.

## Validation

Run `python scripts/validate_documentation_contracts.py`.

CI must fail when source contains a model, declared field, explicit API route, router registration, or registered route surface that is missing from this inventory, or when a stale inventory row remains after source deletion.
