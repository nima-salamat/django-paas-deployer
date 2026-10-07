# Source contract inventory

This document is the canonical machine-checkable inventory for first-party models, declared model fields, API routes, and DRF router registrations.

Source code is authoritative. App-level API/model references explain behavior; this file provides stable source signatures so CI can detect documentation drift.

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|
| `agent` | `src/agent/urls.py` | explicit | `v1/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/agent.md` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/auth/exchange` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/auth/me` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/capabilities` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/cancel` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/logs/export` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/logs` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/rebuild` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/redeploy` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/rollback` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/start` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>/upload` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/<uuid:deployment_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/help` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments/inspect` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/deployments` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/networks/<uuid:network_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/networks` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/openapi.json` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/<uuid:plan_id>/apply` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/<uuid:plan_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/manage/<uuid:plan_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans/manage` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/plans` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/configuration` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/database-credentials` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/databases` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/endpoints` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/environment` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/logs/export` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/logs` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/metrics` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/networks` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/purge-runtime` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/rebuild` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/restart` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions/<uuid:revision_id>/rollback` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions/<uuid:revision_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/revisions` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/secrets` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/files` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/replace` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions/<uuid:session_id>/close` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions/<uuid:session_id>/commands` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell/sessions` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/shell` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/start` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/status` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/stop` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/tools/<str:tool_name>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>/tools` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/<uuid:service_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services/from-plan` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/services` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/skills/<slug:skill_name>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/skills` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/volumes/<uuid:volume_id>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/urls.py` | explicit | `v1/volumes` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<root>` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/<str:action>/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/audit/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/revoke/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/rotate/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/manifest/` | [app API docs](../apps/agent/api.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `scopes/` | [app API docs](../apps/agent/api.md) |
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
| `config` | `src/config/urls.py` | explicit | `media/` | [services API docs](../apps/services/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/<str:key>/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/settings_urls.py` | explicit | `settings/seed/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/urls.py` | explicit | `<uuid:pk>/download/` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/urls.py` | explicit | `images/<path:path>` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/urls.py` | explicit | `messenger/<path:path>` | [app API docs](../apps/core/api-reference.md) |
| `core` | `src/core/urls.py` | explicit | `tickets/<path:path>` | [app API docs](../apps/core/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `logs/<int:pk>/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `logs/<int:pk>/retry/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `logs/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `send/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `stats/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `templates/<int:pk>/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `templates/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `templates/preview/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `custom_emails` | `src/custom_emails/urls.py` | explicit | `users/` | [app API docs](../apps/custom_emails/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<root>` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/cancel/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/download/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/logs/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/logs/export/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/rebuild/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/redeploy/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/reveal_db_credentials/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/rollback/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/start/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `<uuid:pk>/update_db_config/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `config_contract/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `generate_db_credentials/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `inspect_zip/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `name_is_available/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `set_deploy/` | [app API docs](../apps/deploy/api-reference.md) |
| `deploy` | `src/deploy/urls.py` | explicit | `unset_deploy/` | [app API docs](../apps/deploy/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `<root>` | [app API docs](../apps/docs/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `admin/assets/<uuid:asset_id>/` | [app API docs](../apps/docs/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `admin/assets/` | [app API docs](../apps/docs/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `assets/<uuid:asset_id>/` | [app API docs](../apps/docs/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `public/<slug:slug>/` | [app API docs](../apps/docs/api-reference.md) |
| `docs` | `src/docs/urls.py` | explicit | `tree/` | [app API docs](../apps/docs/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `attachments/<int:pk>/download/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `attachments/<int:pk>/view-once/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `blocks/<int:user_id>/unblock/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `blocks/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `contacts/<int:user_id>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `contacts/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/avatar/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/call/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/call/active/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/call/end/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/call/join/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/cleanup/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/delete/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/events/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/invite-links/<int:link_id>/revoke/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/invite-links/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/join-requests/<int:req_id>/action/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/join-requests/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/leave/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/media/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/members/<int:user_id>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/members/<int:user_id>/role/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/members/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/messages/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/messages/search/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/participants/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/pin/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/pinned-messages/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/read/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/scheduled/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/<int:pk>/transfer-ownership/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `conversations/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `groups/<int:pk>/join/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `groups/search/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `join-requests/<int:req_id>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `join/<str:code>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `me/bio/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `me/join-requests/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `me/photo-privacy/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `me/photos/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `me/profile-broadcast/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/cancel-schedule/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/edit/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/forward/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/pin/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/react/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `messages/<int:pk>/readers/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `users/<int:user_id>/profile/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `users/by-username/` | [app API docs](../apps/messenger/api-reference.md) |
| `messenger` | `src/messenger/urls.py` | explicit | `users/search/` | [app API docs](../apps/messenger/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `<root>` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `admin/plans/<uuid:pk>/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `admin/plans/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `plans/<uuid:planId>/apply/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `platforms/` | [app API docs](../apps/plans/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `admin/logging/health/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `admin/purge_service_runtime/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `admin/start_service/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `admin/stop_service/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `force_cancel_deploy/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `purge_service_runtime/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `restart_service/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:pk>/logs/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:pk>/logs/export/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/configuration/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/database-resources/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/databases/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/endpoints/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/environment/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/networks/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/revisions/<uuid:revision_id>/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/revisions/<uuid:revision_id>/rollback/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/revisions/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/secrets/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service/<uuid:service_id>/volume-capabilities/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `service_status/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/access/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/audit/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/audit/export/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/catalog/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/close/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/command/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/download/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/env/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/file/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/health/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/history/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/session/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/session/replace/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/tree/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/<uuid:service_id>/shell/tree/meta/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/groups/<int:group_id>/shares/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/mine/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/share-presets/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/share/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shared/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shares/<uuid:pk>/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shares/<uuid:pk>/events/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shares/<uuid:pk>/leave/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shares/<uuid:pk>/members/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/shares/<uuid:pk>/permissions/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `services/unified/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `start_service/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `stop_service/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `volume/<uuid:pk>/download/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/urls.py` | explicit | `volume/<uuid:pk>/files/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/volume_api_urls.py` | explicit | `<uuid:pk>/download/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/services/volume_api_urls.py` | explicit | `<uuid:pk>/files/` | [app API docs](../apps/services/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `<int:pk>/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `<int:pk>/close/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `<int:pk>/messages/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `<int:pk>/read/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `<root>` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/departments/<int:pk>/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/departments/<int:pk>/members/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/departments/<int:pk>/staff/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/departments/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/staff/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `admin/users/<int:user_id>/memberships/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `attachments/<int:pk>/download/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `context/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `departments/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/<int:pk>/assign/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/<int:pk>/delete/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/<int:pk>/department/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/<int:pk>/priority/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/<int:pk>/status/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/` | [app API docs](../apps/tickets/api-reference.md) |
| `tickets` | `src/tickets/urls.py` | explicit | `staff/stats/` | [app API docs](../apps/tickets/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/me/permissions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/permissions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/tables/<str:model_key>/<str:pk>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/tables/<str:model_key>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/tables/<str:model_key>/fk-search/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/tables/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/profiles/<int:profile_id>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/profiles/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/profiles/reorder/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/rules/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/sessions/<str:session_id>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/sessions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/<int:pk>/sessions/logout-all/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `admin/users/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `change-password/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `password-status/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `remove-password/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `set-password/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `user/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `user/contact-change/<uuid:change_id>/confirm/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/api_urls.py` | explicit | `user/contact-change/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/me/permissions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/permissions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/<int:pk>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/<int:pk>/rules/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/<int:pk>/sessions/<str:session_id>/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/<int:pk>/sessions/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/<int:pk>/sessions/logout-all/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `admin/users/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `password/change/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `password/remove/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `password/set/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `password/status/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `plans/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `profile/delete/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `profile/list/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `profile/order/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `profile/set/` | [app API docs](../apps/users/api-reference.md) |
| `users` | `src/users/urls.py` | explicit | `user/` | [app API docs](../apps/users/api-reference.md) |

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path | Kind |
|---|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | project model class | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | project model class | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | project model class | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | project model class | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `Agent` | project model class | [field reference](../apps/agent/field-reference.md#agent) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | project model class | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | project model class | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | project model class | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | project model class | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `Device` | project model class | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | project model class | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | project model class | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | project model class | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | project model class | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | project model class | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | project model class | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `cms` | `src/cms/models.py` | `HomePage` | project model class | [field reference](../apps/cms/field-reference.md#homepage) |
| `core` | `src/core/models.py` | `CoreSettings` | project model class | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `SystemSetting` | project model class | [field reference](../apps/core/field-reference.md#systemsetting) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | project model class | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | project model class | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | project model class | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | project model class | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | project model class | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | project model class | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | project model class | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `Deploy` | project model class | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | project model class | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | project model class | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | project model class | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | project model class | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | project model class | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | project model class | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `Document` | project model class | [field reference](../apps/docs/field-reference.md#document) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | project model class | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | project model class | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | project model class | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | project model class | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | project model class | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | project model class | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `Block` | project model class | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | project model class | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |
| `messenger` | `src/messenger/models.py` | `CallSession` | project model class | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `Contact` | project model class | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | project model class | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `Conversation` | project model class | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | project model class | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | project model class | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | project model class | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | project model class | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | project model class | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `Message` | project model class | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | project model class | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | project model class | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | project model class | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | project model class | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `UserBio` | project model class | [field reference](../apps/messenger/field-reference.md#userbio) |
| `plans` | `src/plans/models.py` | `Plan` | project model class | [field reference](../apps/plans/field-reference.md#plan) |
| `services` | `src/services/models.py` | `DatabaseCredential` | project model class | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseResource` | project model class | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `PrivateNetwork` | project model class | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | project model class | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | project model class | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | project model class | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | project model class | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServicePortReservation` | project model class | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServiceProcess` | project model class | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceRevision` | project model class | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | project model class | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecret` | project model class | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | project model class | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareMember` | project model class | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShare` | project model class | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `Service` | project model class | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | project model class | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellSession` | project model class | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `Volume` | project model class | [field reference](../apps/services/field-reference.md#volume) |
| `tickets` | `src/tickets/models.py` | `DepartmentMembership` | project model class | [field reference](../apps/tickets/field-reference.md#departmentmembership) |
| `tickets` | `src/tickets/models.py` | `Department` | project model class | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | project model class | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | project model class | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketReadState` | project model class | [field reference](../apps/tickets/field-reference.md#ticketreadstate) |
| `tickets` | `src/tickets/models.py` | `Ticket` | project model class | [field reference](../apps/tickets/field-reference.md#ticket) |
| `users` | `src/users/models.py` | `PermissionMixin` | project model class | [field reference](../apps/users/field-reference.md#permissionmixin) |
| `users` | `src/users/models.py` | `Profile` | project model class | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Receipt` | project model class | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Rule` | project model class | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `User` | project model class | [field reference](../apps/users/field-reference.md#user) |

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `action` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `credential` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `duration_ms` | `PositiveIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `failure_domain` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `http_status` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `request_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `visibility` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `key` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `state` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `Agent` | `description` | `TextField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `disabled_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `name` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `provisioning_source` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `scopes` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `status` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agent) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `deploy` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatch_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatched_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `instance` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `sequence` | `PositiveIntegerField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service_key` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `cancel_requested` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_snapshot` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `deployed_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_code` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_message` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_deadline` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `id` | `UUIDField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `name` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `network` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `secret_config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `slug` | `SlugField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `software_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `stage` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `started_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `status` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `user` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `variant_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `enabled` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `featured_override` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `notes` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_by` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `code` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `contact` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `purpose` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `client` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `name` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `platform` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_by` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `label` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `max_uses` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `token` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `uses_count` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `invite` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `used_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `event` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `extra` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `failure_reason` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `identifier` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `method` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `success` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `username` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `activate_after_successful_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_auto_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_login` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_password_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `auto_activate_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_message` | `TextField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_title` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `max_active_sessions` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `min_password_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_expire_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_max_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_as_second_factor` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_confirm_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_invite_for_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `session_eviction_policy` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `cancelled_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `field` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `new_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `old_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `status` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `verified_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `auth_generation` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `credential_hash` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `device` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `session_id` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `cms` | `src/cms/models.py` | `HomePage` | `body` | `RichTextField` | [field reference](../apps/cms/field-reference.md#homepage) |
| `core` | `src/core/models.py` | `CoreSettings` | `auto_public_url_handling` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_image_build_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_build` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_register_existing` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_retain_after_deploy` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_batch_size` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_cleanup_target_percent` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_global_limit_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_keep_successful_deployments` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_service_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_user_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_cpu` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_ram_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_parallelism` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_pids_limit` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_resource_mode` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_shm_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_slot_lease_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_wait_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `default_public_url_prefix` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `deploy_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_apt` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_composer` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_docker` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_go` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_npm` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_python` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_batch_size` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_interval_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_max_recovery_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_recovery_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_scheduler_lock_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_base_build_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_worker_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `queued_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `shell_idle_timeout_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `stop_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `unexpected_death_grace_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_release_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_usage_warning_percent` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `SystemSetting` | `category` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `created_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `description` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_editable` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_secret` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `key` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `label` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `updated_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value_type` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `body_preview` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `celery_task_id` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `error_message` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `failed_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `is_test` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient_email` | `EmailField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `status` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `template` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `body` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `description` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `is_active` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `name` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `updated_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `acquired_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `base_image` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `deployment_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `released_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `architecture` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `auto_build` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_completed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_count` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_owner_deployment_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_task_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `definition_fingerprint` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `docker_host` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `enabled` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_repository` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_tag` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `last_error_details` | `JSONField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `logical_runtime` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `rebuild_requested_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `rebuild_requested` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `runtime_version` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `source_image` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `status` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `variant` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `deployment` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `last_used_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `pinned` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `reclaim_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `reclaimed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `size_bytes` | `BigIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `user` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `keep_successful_deployments` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `quota_mb` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `retention_days` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `service` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `user` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `deploy` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `details` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `event_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `event_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `exception_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `level` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `progress` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `traceback` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `application_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `base_image_ready_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `base_image_wait_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cancel_requested` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cleanup_failures` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cleanup_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `completed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `config` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `container_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `created_by` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `error_message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `execution_task_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `health_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `network_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_previous_resource_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_resource_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `previous_deploy` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `progress` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `reconciliation_required` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `recovery_metadata` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `release_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `revision` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `rollback_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_revision_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_spec_sha256` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_spec` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `source_revision` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `status_message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `updated_file_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `version` | `DecimalField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `volume_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `worker_heartbeat_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `zip_file` | `FileField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `attempts` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `deployment` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `dispatched_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `event_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `event_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `level` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `next_attempt_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `occurred_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `payload` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `service_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `deployment` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `kind` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `metadata` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `owned` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `retired_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `runtime_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `state` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `enabled` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `last_synced_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `manager_endpoint` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `address` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `cluster` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `cpus` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `desired_availability` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `desired_labels` | `JSONField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `docker_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `hostname` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `labels` | `JSONField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `last_synced_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `manager_reachable` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `memory_bytes` | `BigIntegerField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `observed_availability` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `observed_state` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `role` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `alt` | `CharField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `created_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `document` | `ForeignKey` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `file` | `FileField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `id` | `UUIDField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `kind` | `CharField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `mime_type` | `CharField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `name` | `CharField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `size_bytes` | `PositiveBigIntegerField` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `created_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `description` | `CharField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `icon` | `CharField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `id` | `UUIDField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `name` | `CharField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `order` | `PositiveIntegerField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `parent` | `ForeignKey` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `slug` | `SlugField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `updated_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `Document` | `category` | `ForeignKey` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `content` | `TextField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `created_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `description` | `CharField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `icon` | `CharField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `id` | `UUIDField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `order` | `PositiveIntegerField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `published_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `slug` | `SlugField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `status` | `CharField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `title` | `CharField` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `Document` | `updated_at` | `DateTimeField` | [field reference](../apps/docs/field-reference.md#document) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `active_containers` | `PositiveIntegerField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `active_streams` | `PositiveIntegerField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `buffer_bytes` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `db_ok` | `BooleanField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `dropped_bytes` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `dropped_entries` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `id` | `BigAutoField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `instance_id` | `CharField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `last_error` | `TextField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `last_heartbeat` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `last_successful_ingestion` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `meta` | `JSONField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `redis_ok` | `BooleanField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `status` | `CharField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `updated_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `bytes_deleted` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `bytes_dropped` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `bytes_ingested` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `date` | `DateField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `entries_deleted` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `entries_dropped` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `entries_ingested` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `id` | `BigAutoField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `service_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `byte_size` | `PositiveIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `created_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `deploy_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `fingerprint` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `id` | `BigAutoField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `level` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `message` | `TextField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `seq` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `service_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `stream_id` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `stream` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `truncated` | `BooleanField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `ts` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `container_id` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `container_name` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `created_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `deploy_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `ended_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `heartbeat_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `id` | `BigAutoField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `last_persisted_fingerprint` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `last_persisted_ts` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `last_seq` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `lease_token` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `lease_until` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `owner_id` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `service_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `started_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `status` | `CharField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `updated_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `bytes_dropped` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `current_storage_bytes` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `entries_dropped` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `entry_count` | `BigIntegerField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `last_ingestion_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `service_id` | `UUIDField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `updated_at` | `DateTimeField` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `attachment` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `expires_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `opened_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `Block` | `blocked` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `Block` | `blocker` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `Block` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `call` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `joined_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `left_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `answered_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `duration_seconds` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `end_message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `ended_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `initiator` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `is_video` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `public_id` | `UUIDField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `room_name` | `CharField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `start_message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `started_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `status` | `CharField` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `Contact` | `contact` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `Contact` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `Contact` | `nickname` | `CharField` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `Contact` | `owner` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `can_add_members` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `can_change_info` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `can_pin_messages` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `can_send_media` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `can_send_messages` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `draft_text` | `TextField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `draft_updated_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `is_muted` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `is_pinned` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `joined_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `last_read_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `left_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `pinned_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `role` | `CharField` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `avatar` | `ImageField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `created_by` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `description` | `TextField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `history_visibility` | `CharField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `is_closed` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `is_public` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `last_message_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `members_can_add` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `only_admins_send` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `public_id` | `UUIDField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `requires_approval` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `title` | `CharField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `type` | `CharField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `updated_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `code` | `CharField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `created_by` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `expires_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `is_active` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `max_uses` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `uses` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `decided_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `decided_by` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `status` | `CharField` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `content_type` | `CharField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `duration` | `FloatField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `file` | `FileField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `height` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `is_purged` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `is_spoiler` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `is_view_once` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `kind` | `CharField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `original_filename` | `CharField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `size` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `uploaded_by` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `width` | `PositiveIntegerField` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `emoji` | `CharField` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | `message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | `seen_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `Message` | `body` | `TextField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `client_message_id` | `CharField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `forwarded_from_message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `forwarded_from` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `is_deleted` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `is_edited` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `is_scheduled` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `is_system` | `BooleanField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `reply_to` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `scheduled_for` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `sender` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `Message` | `updated_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `actor` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `call` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `event_id` | `UUIDField` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `event_type` | `CharField` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `payload` | `JSONField` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `conversation` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `message` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `pinned_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `pinned_by` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | `created_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | `privacy` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | `user` | `ForeignKey` | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | `scope` | `CharField` | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | `updated_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | `user` | `OneToOneField` | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `UserBio` | `text` | `CharField` | [field reference](../apps/messenger/field-reference.md#userbio) |
| `messenger` | `src/messenger/models.py` | `UserBio` | `updated_at` | `DateTimeField` | [field reference](../apps/messenger/field-reference.md#userbio) |
| `messenger` | `src/messenger/models.py` | `UserBio` | `user` | `OneToOneField` | [field reference](../apps/messenger/field-reference.md#userbio) |
| `plans` | `src/plans/models.py` | `Plan` | `log_ingest_bytes_per_sec` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_quota_behavior` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_retention_days` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_storage_mb` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_cpu` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_ram` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_storage` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `name` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `persistent_logging` | `BooleanField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `plan_type` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `platform` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `price_per_hour` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `realtime_logging` | `BooleanField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `storage_type` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `database` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `password_ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `username` | `CharField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseResource` | `access_policy` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `database_name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `engine` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `host` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `owner` | `ForeignKey` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `provider_service` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `description` | `TextField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `access_mode` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `database` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `env_prefix` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `exposure` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `hostname` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `process` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `published_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `target_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `tls` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `scope` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `value` | `TextField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `internal` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `endpoint` | `OneToOneField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `host_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServiceProcess` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `entrypoint` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `environment` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `healthcheck` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `process_type` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `replicas` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `resources` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceRevision` | `activated_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `artifact_file` | `FileField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `build_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `config_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `endpoint_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `environment_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `graph_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `network_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `process_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `revision_number` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `runtime_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_keys` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_refs` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_deploy` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `volume_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecret` | `current_version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `description` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `actor` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `message` | `TextField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `is_enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShare` | `admin_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `group` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `is_active` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `preset` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `shared_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `target_user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `Service` | `active_revision` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `build_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deploy_started` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deployed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `desired_state` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `lifecycle_generation` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `plan` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `read_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `runtime_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy` | `OneToOneField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_kind` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `task_id` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `cwd` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `detail` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `exit_code` | `IntegerField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `meta` | `JSONField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `output_preview` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `session` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `success` | `BooleanField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellSession` | `closed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `last_used_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `mode` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `platform` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `root_path` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `token_hash` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `workdir` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `Volume` | `default_bind` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `default_mode` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_attempted_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_error` | `TextField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `released_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service_attachments` | `JSONField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `size_mb` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `tickets` | `src/tickets/models.py` | `DepartmentMembership` | `created_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#departmentmembership) |
| `tickets` | `src/tickets/models.py` | `DepartmentMembership` | `department` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#departmentmembership) |
| `tickets` | `src/tickets/models.py` | `DepartmentMembership` | `is_manager` | `BooleanField` | [field reference](../apps/tickets/field-reference.md#departmentmembership) |
| `tickets` | `src/tickets/models.py` | `DepartmentMembership` | `user` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#departmentmembership) |
| `tickets` | `src/tickets/models.py` | `Department` | `created_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `description` | `TextField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `is_active` | `BooleanField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `name` | `CharField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `order` | `PositiveIntegerField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `slug` | `SlugField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `Department` | `updated_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#department) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `content_type` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `created_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `file` | `FileField` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `message` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `original_filename` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `size` | `PositiveIntegerField` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `ticket` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketAttachment` | `uploaded_by` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketattachment) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `author` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `body` | `TextField` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `created_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `is_staff_reply` | `BooleanField` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `seen_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `ticket` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketMessage` | `updated_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketmessage) |
| `tickets` | `src/tickets/models.py` | `TicketReadState` | `last_read_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketreadstate) |
| `tickets` | `src/tickets/models.py` | `TicketReadState` | `ticket` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketreadstate) |
| `tickets` | `src/tickets/models.py` | `TicketReadState` | `updated_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticketreadstate) |
| `tickets` | `src/tickets/models.py` | `TicketReadState` | `user` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticketreadstate) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `assigned_to` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `closed_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `created_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `department` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `deploy` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `last_message_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `priority` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `public_id` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `service` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `status` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `subject` | `CharField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `updated_at` | `DateTimeField` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `tickets` | `src/tickets/models.py` | `Ticket` | `user` | `ForeignKey` | [field reference](../apps/tickets/field-reference.md#ticket) |
| `users` | `src/users/models.py` | `PermissionMixin` | `is_superuser` | `BooleanField` | [field reference](../apps/users/field-reference.md#permissionmixin) |
| `users` | `src/users/models.py` | `Profile` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `image` | `ImageField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `order` | `IntegerField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Receipt` | `amount` | `DecimalField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `status` | `CharField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Rule` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `rules` | `ArrayField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `user` | `OneToOneField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `User` | `balance` | `DecimalField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `birthdate` | `DateField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `color` | `PositiveSmallIntegerField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `date_joined` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `deletion_requested_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email` | `EmailField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `first_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_active` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_staff` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `last_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `national_id` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `password` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `phone_number_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `phone_number` | `PhoneNumberField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `theme` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `username` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `uuid` | `CharField` | [field reference](../apps/users/field-reference.md#user) |

## Inheritance

See [inherited-model-fields.md](inherited-model-fields.md) for project-wide BaseModel fields and framework/Wagtail inheritance boundaries.

## Validation

Run `python scripts/validate_documentation_contracts.py`.

CI must fail when source contains a model, declared field, explicit API route, router registration, or registered route surface that is missing from this inventory, or when a stale inventory row remains after source deletion.
