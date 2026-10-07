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
