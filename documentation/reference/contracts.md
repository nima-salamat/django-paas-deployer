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
| `agent` | `src/agent/models.py` | `Agent` | project model class | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | project model class | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | project model class | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | project model class | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | project model class | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | project model class | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | project model class | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | project model class | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | project model class | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `Device` | project model class | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | project model class | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | project model class | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | project model class | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | project model class | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | project model class | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | project model class | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `cms` | `src/cms/models.py` | `HomePage` | project model class | [field reference](../apps/cms/field-reference.md#homepage) |
| `core` | `src/core/models.py` | `SystemSetting` | project model class | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `CoreSettings` | project model class | [field reference](../apps/core/field-reference.md#coresettings) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | project model class | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | project model class | [field reference](../apps/custom_emails/field-reference.md#emaillog) |

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|
| `agent` | `src/agent/models.py` | `Agent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `name` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `description` | `TextField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `status` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `provisioning_source` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `scopes` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `disabled_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `credential` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `action` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `request_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `http_status` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `failure_domain` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `visibility` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `duration_ms` | `PositiveIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `key` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `state` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `id` | `UUIDField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `user` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `name` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `slug` | `SlugField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `software_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `variant_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_snapshot` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `secret_config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `status` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_code` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_message` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `deployed_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `stage` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `started_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_deadline` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `cancel_requested` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `network` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `instance` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `deploy` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service_key` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `sequence` | `PositiveIntegerField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatch_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatched_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `enabled` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `featured_override` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `notes` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_by` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_as_second_factor` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_auto_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `auto_activate_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `activate_after_successful_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_invite_for_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_password_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_confirm_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `min_password_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_login` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_message` | `TextField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_title` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_expire_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_max_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `max_active_sessions` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `session_eviction_policy` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `name` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `platform` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `client` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `session_id` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `device` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `credential_hash` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `auth_generation` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `field` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `old_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `new_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `status` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `verified_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `cancelled_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `token` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `label` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_by` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `max_uses` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `uses_count` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `invite` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `used_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `contact` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `purpose` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `code` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `username` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `identifier` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `event` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `method` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `success` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `failure_reason` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `extra` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `cms` | `src/cms/models.py` | `HomePage` | `body` | `RichTextField` | [field reference](../apps/cms/field-reference.md#homepage) |
| `core` | `src/core/models.py` | `SystemSetting` | `key` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value_type` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `category` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `label` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `description` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_secret` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_editable` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `updated_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `created_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_build` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_retain_after_deploy` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_image_build_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_register_existing` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `auto_public_url_handling` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `default_public_url_prefix` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_docker` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_python` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_npm` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_composer` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_apt` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_go` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_resource_mode` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_pids_limit` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_shm_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_parallelism` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_wait_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_cpu` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_ram_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_usage_warning_percent` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_release_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_slot_lease_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `deploy_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `queued_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `stop_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `unexpected_death_grace_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_interval_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_batch_size` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_recovery_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_max_recovery_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_base_build_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_worker_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_scheduler_lock_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_global_limit_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_user_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_service_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_keep_successful_deployments` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_cleanup_target_percent` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_batch_size` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `shell_idle_timeout_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `name` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `body` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `description` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `is_active` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `updated_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient_email` | `EmailField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `template` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `body_preview` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `status` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `error_message` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `is_test` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `failed_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `celery_task_id` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |

## Inheritance

See [inherited-model-fields.md](inherited-model-fields.md) for project-wide BaseModel fields and framework/Wagtail inheritance boundaries.

## Validation

Run `python scripts/validate_documentation_contracts.py`.

CI must fail when source contains a model, declared field, explicit API route, router registration, or registered route surface that is missing from this inventory, or when a stale inventory row remains after source deletion.
