# Source contract inventory

This file is the machine-checkable documentation index for first-party models and HTTP API routes.

**Generation rule:** every inventory row has a stable source signature. CI compares source declarations against these tables and fails when a model, declared field, explicit route, router registration, or router action is added/removed without updating this file.

The detailed app documentation remains the narrative contract. This file answers one narrower question: **does the documented contract inventory contain the thing that exists in source?**

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
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/<str:action>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/audit/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/<uuid:credential_id>/revoke/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/credentials/rotate/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `<uuid:agent_id>/manifest/` | [app API docs](../apps/agent/api-reference.md) |
| `agent` | `src/agent/user_urls.py` | explicit | `` | [app API docs](../apps/agent/api-reference.md) |
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
| `plans` | `src/plans/urls.py` | explicit | `admin/plans/<uuid:pk>/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `admin/plans/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `plans/<uuid:planId>/apply/` | [app API docs](../apps/plans/api-reference.md) |
| `plans` | `src/plans/urls.py` | explicit | `platforms/` | [app API docs](../apps/plans/api-reference.md) |
| `services` | `src/config/urls.py` | explicit | `api/networks/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/config/urls.py` | explicit | `api/services/service_status/` | [app API docs](../apps/services/api-reference.md) |
| `services` | `src/config/urls.py` | explicit | `api/volumes/` | [app API docs](../apps/services/api-reference.md) |
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
| `services` | `src/services/urls.py` | `ServiceViewSet` | `service` | false | GET,POST | `/service/` | CRUD list/create |
| `services` | `src/services/urls.py` | `ServiceViewSet` | `service` | true | GET,PUT,PATCH,DELETE | `/service/{pk}/` | CRUD detail |
| `services` | `src/services/urls.py` | `PrivateNetworkViewSet` | `networks` | false | GET,POST | `/networks/` | CRUD list/create |
| `services` | `src/services/urls.py` | `PrivateNetworkViewSet` | `networks` | true | GET,PUT,PATCH,DELETE | `/networks/{pk}/` | CRUD detail |
| `services` | `src/services/urls.py` | `VolumeViewSet` | `volume` | false | GET,POST | `/volume/` | CRUD list/create |
| `services` | `src/services/urls.py` | `VolumeViewSet` | `volume` | true | GET,PUT,PATCH,DELETE | `/volume/{pk}/` | CRUD detail |
| `services` | `src/services/urls.py` | `AdminServiceViewSet` | `admin/services` | false | GET,POST | `/admin/services/` | Admin CRUD list/create |
| `services` | `src/services/urls.py` | `AdminServiceViewSet` | `admin/services` | true | GET,PUT,PATCH,DELETE | `/admin/services/{pk}/` | Admin CRUD detail |
| `services` | `src/services/urls.py` | `AdminPrivateNetworkViewSet` | `admin/networks` | false | GET,POST | `/admin/networks/` | Admin CRUD list/create |
| `services` | `src/services/urls.py` | `AdminPrivateNetworkViewSet` | `admin/networks` | true | GET,PUT,PATCH,DELETE | `/admin/networks/{pk}/` | Admin CRUD detail |
| `services` | `src/services/urls.py` | `AdminVolumeViewSet` | `admin/volumes` | false | GET,POST | `/admin/volumes/` | Admin CRUD list/create |
| `services` | `src/services/urls.py` | `AdminVolumeViewSet` | `admin/volumes` | true | GET,PUT,PATCH,DELETE | `/admin/volumes/{pk}/` | Admin CRUD detail |
| `services` | `src/services/api/user_services.py` | `VolumeViewSet` | `volume` | true | POST | `/volume/{pk}/detach/` | custom action |
| `services` | `src/services/api/user_services.py` | `VolumeViewSet` | `volume` | true | POST | `/volume/{pk}/attach/` | custom action |
| `services` | `src/services/volume_api_urls.py` | `VolumeViewSet` | `` | false | GET,POST | `/{pk?}/` | Alias router root; standard detail paths under /api/volumes/ |
| `services` | `src/services/network_api_urls.py` | `PrivateNetworkViewSet` | `` | false | GET,POST | `/{pk?}/` | Alias router root; standard detail paths under /api/networks/ |
| `docs` | `src/docs/urls.py` | `DocumentAdminViewSet` | `admin/documents` | false | GET,POST | `/admin/documents/` | CRUD list/create |
| `docs` | `src/docs/urls.py` | `DocumentAdminViewSet` | `admin/documents` | true | GET,PUT,PATCH,DELETE | `/admin/documents/{pk}/` | CRUD detail |
| `docs` | `src/docs/apis.py` | `DocumentAdminViewSet` | `admin/documents` | false | POST | `/admin/documents/reorder/` | custom action |
| `docs` | `src/docs/apis.py` | `DocumentAdminViewSet` | `admin/documents` | true | POST | `/admin/documents/{pk}/publish/` | custom action |
| `docs` | `src/docs/apis.py` | `DocumentAdminViewSet` | `admin/documents` | true | POST | `/admin/documents/{pk}/unpublish/` | custom action |
| `docs` | `src/docs/urls.py` | `CategoryAdminViewSet` | `admin/categories` | false | GET,POST | `/admin/categories/` | CRUD list/create |
| `docs` | `src/docs/urls.py` | `CategoryAdminViewSet` | `admin/categories` | true | GET,PUT,PATCH,DELETE | `/admin/categories/{pk}/` | CRUD detail |
| `docs` | `src/docs/apis.py` | `CategoryAdminViewSet` | `admin/categories` | false | POST | `/admin/categories/reorder/` | custom action |
| `docs` | `src/docs/apis.py` | `CategoryAdminViewSet` | `admin/categories` | false | GET | `/admin/categories/tree/` | custom action |


