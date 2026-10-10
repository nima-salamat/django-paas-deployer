# Documentation coverage manifest

Maintained against the `master` source tree; the latest documentation refresh was committed on 2026-10-07. Source code is authoritative. This is a reviewable source-surface inventory, not a claim that every module requires a separate Markdown file.

## Acceptance equation

Every production source surface must be mapped to its owning canonical document or explicitly classified as trivial, internal, generated, or compatibility-excluded with a reason.

## Installed first-party applications

- [agent](./agent/README.md)
- [users](./users/README.md)
- [auth_users](./auth_users/README.md)
- [services](./services/README.md)
- [plans](./plans/README.md)
- [deploy](./deploy/README.md)
- [deployments](./deployments/README.md)
- [logs](./logs/README.md)
- [app_catalog](./app_catalog/README.md)
- [messenger](./messenger/README.md)
- [tickets](./tickets/README.md)
- [custom_emails](./custom_emails/README.md)
- [docs](./docs/README.md)
- [core](./core/README.md)
- [cms](./cms/README.md)

## Source inventory

| Application | Production Python modules | Canonical documentation |
|---|---:|---|
| `agent` | 36 | [agent](./agent/README.md) |
| `users` | 19 | [users](./users/README.md) |
| `auth_users` | 23 | [auth_users](./auth_users/README.md) |
| `services` | 36 | [services](./services/README.md) |
| `plans` | 13 | [plans](./plans/README.md) |
| `deploy` | 24 | [deploy](./deploy/README.md) |
| `deployments` | 118 | [deployments](./deployments/README.md) |
| `logs` | 12 | [logs](./logs/README.md) |
| `app_catalog` | 18 | [app_catalog](./app_catalog/README.md) |
| `messenger` | 34 | [messenger](./messenger/README.md) |
| `tickets` | 21 | [tickets](./tickets/README.md) |
| `custom_emails` | 12 | [custom_emails](./custom_emails/README.md) |
| `docs` | 9 | [docs](./docs/README.md) |
| `core` | 31 | [core](./core/README.md) |
| `cms` | 9 | [cms](./cms/README.md) |
| **Total** | **415** | **15 app boundaries** |

### Module-level inventory

#### users

- `src/users/__init__.py` → [users](./users/README.md)
- `src/users/admin.py` → [users](./users/README.md)
- `src/users/admin_apis.py` → [users](./users/README.md)
- `src/users/admin_tables_api.py` → [users](./users/README.md)
- `src/users/api/__init__.py` → [users](./users/README.md)
- `src/users/api_urls.py` → [users](./users/README.md)
- `src/users/apis.py` → [users](./users/README.md)
- `src/users/apps.py` → [users](./users/README.md)
- `src/users/cache_signals.py` → [users](./users/README.md)
- `src/users/contact_api.py` → [users](./users/README.md)
- `src/users/models.py` → [users](./users/README.md)
- `src/users/serializers.py` → [users](./users/README.md)
- `src/users/signals.py` → [users](./users/README.md)
- `src/users/tasks.py` → [users](./users/README.md)
- `src/users/urls.py` → [users](./users/README.md)
- `src/users/validators.py` → [users](./users/README.md)
- `src/users/views.py` → [users](./users/README.md)
- `src/users/wagtail_admin/__init__.py` → [users](./users/README.md)
- `src/users/wagtail_admin/models.py` → [users](./users/README.md)
- `src/users/wagtail_hooks.py` → [users](./users/README.md)

#### auth_users

- `src/auth_users/__init__.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/admin.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/admin_login_settings.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/__init__.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/aliases_admin.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/auth_flow.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/invites.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/recovery.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/api/settings.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/apis.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/apps.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/authentication.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/deletion_signals.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/models.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/services.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/session_api.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/session_auth.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/token_serializers.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/token_views.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/urls.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/views.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/wagtail_admin/__init__.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/wagtail_admin/models.py` → [auth_users](./auth_users/README.md)
- `src/auth_users/wagtail_hooks.py` → [auth_users](./auth_users/README.md)

#### services

- `src/services/__init__.py` → [services](./services/README.md)
- `src/services/admin.py` → [services](./services/README.md)
- `src/services/api/__init__.py` → [services](./services/README.md)
- `src/services/api/admin_services.py` → [services](./services/README.md)
- `src/services/api/common.py` → [services](./services/README.md)
- `src/services/api/configuration.py` → [services](./services/README.md)
- `src/services/api/runtime.py` → [services](./services/README.md)
- `src/services/api/sharing.py` → [services](./services/README.md)
- `src/services/api/shell.py` → [services](./services/README.md)
- `src/services/api/user_services.py` → [services](./services/README.md)
- `src/services/api/volume_files.py` → [services](./services/README.md)
- `src/services/apis.py` → [services](./services/README.md)
- `src/services/apps.py` → [services](./services/README.md)
- `src/services/cache_signals.py` → [services](./services/README.md)
- `src/services/consumers.py` → [services](./services/README.md)
- `src/services/html_urls.py` → [services](./services/README.md)
- `src/services/lifecycle/__init__.py` → [services](./services/README.md)
- `src/services/lifecycle/authority.py` → [services](./services/README.md)
- `src/services/lifecycle/fencing.py` → [services](./services/README.md)
- `src/services/models.py` → [services](./services/README.md)
- `src/services/network_api_urls.py` → [services](./services/README.md)
- `src/services/ports.py` → [services](./services/README.md)
- `src/services/revisioning.py` → [services](./services/README.md)
- `src/services/routing.py` → [services](./services/README.md)
- `src/services/secret_store.py` → [services](./services/README.md)
- `src/services/serializers.py` → [services](./services/README.md)
- `src/services/share_cleanup.py` → [services](./services/README.md)
- `src/services/share_permissions.py` → [services](./services/README.md)
- `src/services/shell.py` → [services](./services/README.md)
- `src/services/signals.py` → [services](./services/README.md)
- `src/services/urls.py` → [services](./services/README.md)
- `src/services/views.py` → [services](./services/README.md)
- `src/services/volume_api_urls.py` → [services](./services/README.md)
- `src/services/wagtail_admin/__init__.py` → [services](./services/README.md)
- `src/services/wagtail_admin/models.py` → [services](./services/README.md)
- `src/services/wagtail_hooks.py` → [services](./services/README.md)

#### plans

- `src/plans/__init__.py` → [plans](./plans/README.md)
- `src/plans/admin.py` → [plans](./plans/README.md)
- `src/plans/apis.py` → [plans](./plans/README.md)
- `src/plans/apps.py` → [plans](./plans/README.md)
- `src/plans/cache_signals.py` → [plans](./plans/README.md)
- `src/plans/html_urls.py` → [plans](./plans/README.md)
- `src/plans/models.py` → [plans](./plans/README.md)
- `src/plans/serializers.py` → [plans](./plans/README.md)
- `src/plans/urls.py` → [plans](./plans/README.md)
- `src/plans/views.py` → [plans](./plans/README.md)
- `src/plans/wagtail_admin/__init__.py` → [plans](./plans/README.md)
- `src/plans/wagtail_admin/models.py` → [plans](./plans/README.md)
- `src/plans/wagtail_hooks.py` → [plans](./plans/README.md)

#### deploy

- `src/deploy/__init__.py` → [deploy](./deploy/README.md)
- `src/deploy/admin.py` → [deploy](./deploy/README.md)
- `src/deploy/apis.py` → [deploy](./deploy/README.md)
- `src/deploy/apps.py` → [deploy](./deploy/README.md)
- `src/deploy/base_images.py` → [deploy](./deploy/README.md)
- `src/deploy/daily_limits.py` → [deploy](./deploy/README.md)
- `src/deploy/db_router.py` → [deploy](./deploy/README.md)
- `src/deploy/deployment_state.py` → [deploy](./deploy/README.md)
- `src/deploy/event_pipeline.py` → [deploy](./deploy/README.md)
- `src/deploy/log_retention.py` → [deploy](./deploy/README.md)
- `src/deploy/management/__init__.py` → [deploy](./deploy/README.md)
- `src/deploy/management/commands/__init__.py` → [deploy](./deploy/README.md)
- `src/deploy/management/commands/migrate_deployment_logs.py` → [deploy](./deploy/README.md)
- `src/deploy/management/commands/setup_deployment_log_db.py` → [deploy](./deploy/README.md)
- `src/deploy/models.py` → [deploy](./deploy/README.md)
- `src/deploy/naming.py` → [deploy](./deploy/README.md)
- `src/deploy/serializers.py` → [deploy](./deploy/README.md)
- `src/deploy/signals.py` → [deploy](./deploy/README.md)
- `src/deploy/urls.py` → [deploy](./deploy/README.md)
- `src/deploy/views.py` → [deploy](./deploy/README.md)
- `src/deploy/wagtail_admin/__init__.py` → [deploy](./deploy/README.md)
- `src/deploy/wagtail_admin/models.py` → [deploy](./deploy/README.md)
- `src/deploy/wagtail_admin/views.py` → [deploy](./deploy/README.md)
- `src/deploy/wagtail_hooks.py` → [deploy](./deploy/README.md)

#### deployments

- `src/deployments/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/application/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/application/cancel.py` → [deployments](./deployments/README.md)
- `src/deployments/application/cancellation.py` → [deployments](./deployments/README.md)
- `src/deployments/application/context.py` → [deployments](./deployments/README.md)
- `src/deployments/application/lifecycle.py` → [deployments](./deployments/README.md)
- `src/deployments/application/strategies.py` → [deployments](./deployments/README.md)
- `src/deployments/apps.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/exceptions.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/helpers.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/monitoring/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/monitoring/actions.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/monitoring/policies.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/schedules.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/service_status.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/services/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/services/deploy_service.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/services/stop_service.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/tasks.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/validators.py` → [deployments](./deployments/README.md)
- `src/deployments/celery/waiters.py` → [deployments](./deployments/README.md)
- `src/deployments/common/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/common/build_slots.py` → [deployments](./deployments/README.md)
- `src/deployments/common/config.py` → [deployments](./deployments/README.md)
- `src/deployments/common/deployment_profile.py` → [deployments](./deployments/README.md)
- `src/deployments/common/exceptions.py` → [deployments](./deployments/README.md)
- `src/deployments/common/resource_policy.py` → [deployments](./deployments/README.md)
- `src/deployments/common/retry.py` → [deployments](./deployments/README.md)
- `src/deployments/common/security.py` → [deployments](./deployments/README.md)
- `src/deployments/common/state_machine.py` → [deployments](./deployments/README.md)
- `src/deployments/consumers.py` → [deployments](./deployments/README.md)
- `src/deployments/core/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/cleanup.py` → [deployments](./deployments/README.md)
- `src/deployments/core/container_logs.py` → [deployments](./deployments/README.md)
- `src/deployments/core/converter.py` → [deployments](./deployments/README.md)
- `src/deployments/core/db_deployer.py` → [deployments](./deployments/README.md)
- `src/deployments/core/deploy.py` → [deployments](./deployments/README.md)
- `src/deployments/core/deployment_logger.py` → [deployments](./deployments/README.md)
- `src/deployments/core/dockerfile.py` → [deployments](./deployments/README.md)
- `src/deployments/core/entrypoints.py` → [deployments](./deployments/README.md)
- `src/deployments/core/exceptions.py` → [deployments](./deployments/README.md)
- `src/deployments/core/health.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/client_manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/container_manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/image_manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/network_manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/manager/volume_manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/orchestrator.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platform_bridge.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/base/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/base/platform.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/base/schema.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/generic.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/go/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/go/go_plat.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/inspector.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/loader.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/angular.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/base_node.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/express.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/nextjs.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/react.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/vite.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/node/vue.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/php/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/php/base_php.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/php/laravel.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/python/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/python/base_python.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/python/django.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/python/fastapi_plat.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/python/flask.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/registry.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/static/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/platforms/static/static_plat.py` → [deployments](./deployments/README.md)
- `src/deployments/core/project_model.py` → [deployments](./deployments/README.md)
- `src/deployments/core/rollback.py` → [deployments](./deployments/README.md)
- `src/deployments/core/runtime_graph.py` → [deployments](./deployments/README.md)
- `src/deployments/core/sink.py` → [deployments](./deployments/README.md)
- `src/deployments/core/state/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/core/state/locks.py` → [deployments](./deployments/README.md)
- `src/deployments/core/state/manager.py` → [deployments](./deployments/README.md)
- `src/deployments/core/swarm.py` → [deployments](./deployments/README.md)
- `src/deployments/core/types.py` → [deployments](./deployments/README.md)
- `src/deployments/core/validation.py` → [deployments](./deployments/README.md)
- `src/deployments/core/volume_storage.py` → [deployments](./deployments/README.md)
- `src/deployments/core/volumes.py` → [deployments](./deployments/README.md)
- `src/deployments/infrastructure/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/infrastructure/django_cancellation.py` → [deployments](./deployments/README.md)
- `src/deployments/infrastructure/django_lifecycle.py` → [deployments](./deployments/README.md)
- `src/deployments/infrastructure/django_runtime.py` → [deployments](./deployments/README.md)
- `src/deployments/management/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/management/commands/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/management/commands/consume_docker_events.py` → [deployments](./deployments/README.md)
- `src/deployments/management/commands/run_log_collector.py` → [deployments](./deployments/README.md)
- `src/deployments/planning/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/planning/bridge.py` → [deployments](./deployments/README.md)
- `src/deployments/planning/configuration.py` → [deployments](./deployments/README.md)
- `src/deployments/planning/plan.py` → [deployments](./deployments/README.md)
- `src/deployments/planning/provenance.py` → [deployments](./deployments/README.md)
- `src/deployments/reconciliation/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/reconciliation/planner.py` → [deployments](./deployments/README.md)
- `src/deployments/routing.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/capabilities.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/contract.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/errors.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/execution_contract.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/fake.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/identity.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/observations.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/registry.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/swarm/__init__.py` → [deployments](./deployments/README.md)
- `src/deployments/runtime/swarm/adapter.py` → [deployments](./deployments/README.md)

- `src/deployments/common/docker_identity.py` → [deployments](./deployments/README.md)

#### logs

- `src/logs/__init__.py` → [logs](./logs/README.md)
- `src/logs/admin_api.py` → [logs](./logs/README.md)
- `src/logs/apps.py` → [logs](./logs/README.md)
- `src/logs/exceptions.py` → [logs](./logs/README.md)
- `src/logs/ingestion.py` → [logs](./logs/README.md)
- `src/logs/admin.py` → [logs](./logs/README.md)
- `src/logs/models.py` → [logs](./logs/README.md)
- `src/logs/policy.py` → [logs](./logs/README.md)
- `src/logs/query.py` → [logs](./logs/README.md)
- `src/logs/realtime.py` → [logs](./logs/README.md)
- `src/logs/retention.py` → [logs](./logs/README.md)
- `src/logs/tasks.py` → [logs](./logs/README.md)
- `src/logs/usage.py` → [logs](./logs/README.md)

#### agent

- `src/agent/admin.py` → [agent](./agent/README.md)
- `src/agent/admin_actions.py` → [agent](./agent/README.md)
- `src/agent/apis.py` → [agent](./agent/README.md)
- `src/agent/apis/base.py` → [agent](./agent/README.md)
- `src/agent/apis/configuration.py` → [agent](./agent/README.md)
- `src/agent/apis/deployments.py` → [agent](./agent/README.md)
- `src/agent/apis/helpers.py` → [agent](./agent/README.md)
- `src/agent/apis/identity.py` → [agent](./agent/README.md)
- `src/agent/apis/networks.py` → [agent](./agent/README.md)
- `src/agent/apis/plans.py` → [agent](./agent/README.md)
- `src/agent/apis/runtime_tools.py` → [agent](./agent/README.md)
- `src/agent/apis/services.py` → [agent](./agent/README.md)
- `src/agent/apis/shell.py` → [agent](./agent/README.md)
- `src/agent/apis/skills.py` → [agent](./agent/README.md)
- `src/agent/apis/volumes.py` → [agent](./agent/README.md)
- `src/agent/application.py` → [agent](./agent/README.md)
- `src/agent/apps.py` → [agent](./agent/README.md)
- `src/agent/authentication.py` → [agent](./agent/README.md)
- `src/agent/contracts.py` → [agent](./agent/README.md)
- `src/agent/errors.py` → [agent](./agent/README.md)
- `src/agent/manifest.py` → [agent](./agent/README.md)
- `src/agent/models.py` → [agent](./agent/README.md)
- `src/agent/openapi.py` → [agent](./agent/README.md)
- `src/agent/permissions.py` → [agent](./agent/README.md)
- `src/agent/runtime_tools.py` → [agent](./agent/README.md)
- `src/agent/scopes.py` → [agent](./agent/README.md)
- `src/agent/security.py` → [agent](./agent/README.md)
- `src/agent/skills.py` → [agent](./agent/README.md)
- `src/agent/tasks.py` → [agent](./agent/README.md)
- `src/agent/throttling.py` → [agent](./agent/README.md)
- `src/agent/urls.py` → [agent](./agent/README.md)
- `src/agent/user_api.py` → [agent](./agent/README.md)
- `src/agent/user_urls.py` → [agent](./agent/README.md)
- `src/agent/views.py` → [agent](./agent/README.md)
- `src/agent/wagtail_admin/models.py` → [agent](./agent/README.md)
- `src/agent/wagtail_hooks.py` → [agent](./agent/README.md)

#### app_catalog

- `src/app_catalog/__init__.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/apis.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/apps.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/catalog.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/compatibility.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/compose.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/compose_catalog.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/executor.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/management/__init__.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/management/commands/__init__.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/management/commands/migrate_service_domain.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/admin.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/models.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/plan.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/serializers.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/services.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/source_loader.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/tasks.py` → [app_catalog](./app_catalog/README.md)
- `src/app_catalog/urls.py` → [app_catalog](./app_catalog/README.md)

#### messenger

- `src/messenger/__init__.py` → [messenger](./messenger/README.md)
- `src/messenger/admin.py` → [messenger](./messenger/README.md)
- `src/messenger/api/__init__.py` → [messenger](./messenger/README.md)
- `src/messenger/api/calls.py` → [messenger](./messenger/README.md)
- `src/messenger/api/common.py` → [messenger](./messenger/README.md)
- `src/messenger/api/contacts.py` → [messenger](./messenger/README.md)
- `src/messenger/api/conversations.py` → [messenger](./messenger/README.md)
- `src/messenger/api/events.py` → [messenger](./messenger/README.md)
- `src/messenger/api/groups.py` → [messenger](./messenger/README.md)
- `src/messenger/api/invites.py` → [messenger](./messenger/README.md)
- `src/messenger/api/media.py` → [messenger](./messenger/README.md)
- `src/messenger/api/members.py` → [messenger](./messenger/README.md)
- `src/messenger/api/messages.py` → [messenger](./messenger/README.md)
- `src/messenger/api/pins.py` → [messenger](./messenger/README.md)
- `src/messenger/api/topics.py` → [messenger](./messenger/README.md)
- `src/messenger/api/profile.py` → [messenger](./messenger/README.md)
- `src/messenger/apis.py` → [messenger](./messenger/README.md)
- `src/messenger/apps.py` → [messenger](./messenger/README.md)
- `src/messenger/call_state.py` → [messenger](./messenger/README.md)
- `src/messenger/celery.py` → [messenger](./messenger/README.md)
- `src/messenger/consumers.py` → [messenger](./messenger/README.md)
- `src/messenger/events.py` → [messenger](./messenger/README.md)
- `src/messenger/message_cache.py` → [messenger](./messenger/README.md)
- `src/messenger/models.py` → [messenger](./messenger/README.md)
- `src/messenger/routing.py` → [messenger](./messenger/README.md)
- `src/messenger/serializers.py` → [messenger](./messenger/README.md)
- `src/messenger/signals.py` → [messenger](./messenger/README.md)
- `src/messenger/tasks.py` → [messenger](./messenger/README.md)
- `src/messenger/urls.py` → [messenger](./messenger/README.md)
- `src/messenger/utils.py` → [messenger](./messenger/README.md)
- `src/messenger/views_admin.py` → [messenger](./messenger/README.md)
- `src/messenger/wagtail_admin/__init__.py` → [messenger](./messenger/README.md)
- `src/messenger/wagtail_admin/models.py` → [messenger](./messenger/README.md)
- `src/messenger/wagtail_hooks.py` → [messenger](./messenger/README.md)

#### tickets

- `src/tickets/__init__.py` → [tickets](./tickets/README.md)
- `src/tickets/admin.py` → [tickets](./tickets/README.md)
- `src/tickets/api/__init__.py` → [tickets](./tickets/README.md)
- `src/tickets/api/admin_tickets.py` → [tickets](./tickets/README.md)
- `src/tickets/api/common.py` → [tickets](./tickets/README.md)
- `src/tickets/api/staff_tickets.py` → [tickets](./tickets/README.md)
- `src/tickets/api/user_tickets.py` → [tickets](./tickets/README.md)
- `src/tickets/apis.py` → [tickets](./tickets/README.md)
- `src/tickets/apps.py` → [tickets](./tickets/README.md)
- `src/tickets/cache_signals.py` → [tickets](./tickets/README.md)
- `src/tickets/consumers.py` → [tickets](./tickets/README.md)
- `src/tickets/models.py` → [tickets](./tickets/README.md)
- `src/tickets/permissions.py` → [tickets](./tickets/README.md)
- `src/tickets/routing.py` → [tickets](./tickets/README.md)
- `src/tickets/serializers.py` → [tickets](./tickets/README.md)
- `src/tickets/signals.py` → [tickets](./tickets/README.md)
- `src/tickets/urls.py` → [tickets](./tickets/README.md)
- `src/tickets/utils.py` → [tickets](./tickets/README.md)
- `src/tickets/wagtail_admin/__init__.py` → [tickets](./tickets/README.md)
- `src/tickets/wagtail_admin/models.py` → [tickets](./tickets/README.md)
- `src/tickets/wagtail_hooks.py` → [tickets](./tickets/README.md)

#### custom_emails

- `src/custom_emails/__init__.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/admin.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/apis.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/apps.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/models.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/serializers.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/services.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/tasks.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/urls.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/wagtail_admin/__init__.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/wagtail_admin/models.py` → [custom_emails](./custom_emails/README.md)
- `src/custom_emails/wagtail_hooks.py` → [custom_emails](./custom_emails/README.md)

#### docs

- `src/docs/__init__.py` → [docs](./docs/README.md)
- `src/docs/admin.py` → [docs](./docs/README.md)
- `src/docs/apis.py` → [docs](./docs/README.md)
- `src/docs/apps.py` → [docs](./docs/README.md)
- `src/docs/models.py` → [docs](./docs/README.md)
- `src/docs/serializers.py` → [docs](./docs/README.md)
- `src/docs/test_ordering.py` → [docs](./docs/README.md)
- `src/docs/test_public_assets.py` → [docs](./docs/README.md)
- `src/docs/urls.py` → [docs](./docs/README.md)

#### core

- `src/core/__init__.py` → [core](./core/README.md)
- `src/core/admin.py` → [core](./core/README.md)
- `src/core/api_renderers.py` → [core](./core/README.md)
- `src/core/apis.py` → [core](./core/README.md)
- `src/core/apis_settings.py` → [core](./core/README.md)
- `src/core/app_cache.py` → [core](./core/README.md)
- `src/core/apps.py` → [core](./core/README.md)
- `src/core/async_api.py` → [core](./core/README.md)
- `src/core/base/BaseModel.py` → [core](./core/README.md)
- `src/core/base/__init__.py` → [core](./core/README.md)
- `src/core/global_settings/__init__.py` → [core](./core/README.md)
- `src/core/global_settings/config.py` → [core](./core/README.md)
- `src/core/initial_config.py` → [core](./core/README.md)
- `src/core/django_admin.py` → [core](./core/README.md)
- `src/core/models.py` → [core](./core/README.md)
- `src/core/production_errors.py` → [core](./core/README.md)
- `src/core/settings_service.py` → [core](./core/README.md)
- `src/core/settings_urls.py` → [core](./core/README.md)
- `src/core/signals.py` → [core](./core/README.md)
- `src/core/system_metrics.py` → [core](./core/README.md)
- `src/core/tasks/__init__.py` → [core](./core/README.md)
- `src/core/tasks/email.py` → [core](./core/README.md)
- `src/core/tasks/zip_utils.py` → [core](./core/README.md)
- `src/core/throttling.py` → [core](./core/README.md)
- `src/core/urls.py` → [core](./core/README.md)
- `src/core/utils.py` → [core](./core/README.md)
- `src/core/wagtail_admin/__init__.py` → [core](./core/README.md)
- `src/core/wagtail_admin/models.py` → [core](./core/README.md)
- `src/core/wagtail_admin/panels.py` → [core](./core/README.md)
- `src/core/wagtail_admin/universal_models.py` → [core](./core/README.md)
- `src/core/wagtail_admin/views.py` → [core](./core/README.md)
- `src/core/wagtail_hooks.py` → [core](./core/README.md)

#### cms

- `src/cms/__init__.py` → [cms](./cms/README.md)
- `src/cms/apps.py` → [cms](./cms/README.md)
- `src/cms/forms.py` → [cms](./cms/README.md)
- `src/cms/management/commands/setup_wagtail_site.py` → [cms](./cms/README.md)
- `src/cms/admin.py` → [cms](./cms/README.md)
- `src/cms/models.py` → [cms](./cms/README.md)
- `src/cms/viewsets.py` → [cms](./cms/README.md)
- `src/cms/wagtail_admin/__init__.py` → [cms](./cms/README.md)
- `src/cms/wagtail_admin/utils.py` → [cms](./cms/README.md)
- `src/cms/wagtail_hooks.py` → [cms](./cms/README.md)

## Non-ORM contracts

The `deployments`, `app_catalog`, `services`, `deploy`, and `core` packages contain architectural contracts that are not Django models. Their canonical documentation covers dataclasses, enums, protocols, typed configuration/planning objects, runtime contracts, state-machine objects, and adapters. The validator inventories these definitions from Python AST rather than relying on a hand-maintained list.

Key deployment contracts include `ResolvedConfiguration`, `ConfigurationLayer`, `DeploymentPlan`, `RuntimeContract`, `RuntimeSelection`, `RuntimeHandle`, `RuntimeOperationResult`, `RuntimeIdentity`, `RuntimeCapabilities`, and `RuntimeAvailability`.

## Catalog assets

There are **58** YAML/TOML catalog assets under `src/app_catalog/catalog/`. They are classified by source location: first-party active definitions, root compatibility/legacy definitions, legacy/experimental definitions, and generated compatibility/reporting JSON.

- `src/app_catalog/catalog/docmost.yaml`
- `src/app_catalog/catalog/first_party/activepieces.yaml`
- `src/app_catalog/catalog/first_party/appsmith.yaml`
- `src/app_catalog/catalog/first_party/audiobookshelf.yaml`
- `src/app_catalog/catalog/first_party/bookstack.yaml`
- `src/app_catalog/catalog/first_party/castopod.yaml`
- `src/app_catalog/catalog/first_party/chatwoot.yaml`
- `src/app_catalog/catalog/first_party/cloudbeaver.yaml`
- `src/app_catalog/catalog/first_party/code-server.yaml`
- `src/app_catalog/catalog/first_party/directus-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/docmost.yaml`
- `src/app_catalog/catalog/first_party/docuseal-with-postgres.yaml`
- `src/app_catalog/catalog/first_party/dolibarr.yaml`
- `src/app_catalog/catalog/first_party/drupal-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/easyappointments.yaml`
- `src/app_catalog/catalog/first_party/freshrss-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/ghost.yaml`
- `src/app_catalog/catalog/first_party/grafana-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/homebox.yaml`
- `src/app_catalog/catalog/first_party/joplin.yaml`
- `src/app_catalog/catalog/first_party/keycloak-with-postgres.yaml`
- `src/app_catalog/catalog/first_party/matrix-synapse-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/mattermost.yaml`
- `src/app_catalog/catalog/first_party/mealie.yaml`
- `src/app_catalog/catalog/first_party/meilisearch.yaml`
- `src/app_catalog/catalog/first_party/n8n-with-postgres-and-worker.yaml`
- `src/app_catalog/catalog/first_party/nextcloud-with-postgres.yaml`
- `src/app_catalog/catalog/first_party/nocodb.yaml`
- `src/app_catalog/catalog/first_party/odoo.yaml`
- `src/app_catalog/catalog/first_party/open-webui.yaml`
- `src/app_catalog/catalog/first_party/postiz.yaml`
- `src/app_catalog/catalog/first_party/redmine.yaml`
- `src/app_catalog/catalog/first_party/rocketchat.yaml`
- `src/app_catalog/catalog/first_party/stirling-pdf.yaml`
- `src/app_catalog/catalog/first_party/strapi.yaml`
- `src/app_catalog/catalog/first_party/umami.yaml`
- `src/app_catalog/catalog/first_party/uptime-kuma.yaml`
- `src/app_catalog/catalog/first_party/vaultwarden.yaml`
- `src/app_catalog/catalog/first_party/vikunja-with-postgresql.yaml`
- `src/app_catalog/catalog/first_party/wikijs.yaml`
- `src/app_catalog/catalog/first_party/wordpress-with-mariadb.yaml`
- `src/app_catalog/catalog/forgejo-with-postgresql.yaml`
- `src/app_catalog/catalog/legacy_experimental/docmost.yaml`
- `src/app_catalog/catalog/legacy_experimental/forgejo-with-postgresql.yaml`
- `src/app_catalog/catalog/legacy_experimental/mattermost.toml`
- `src/app_catalog/catalog/legacy_experimental/minio.yaml`
- `src/app_catalog/catalog/legacy_experimental/n8n-with-postgres-and-worker.yaml`
- `src/app_catalog/catalog/legacy_experimental/synapse-mysql-mariadb.toml`
- `src/app_catalog/catalog/legacy_experimental/synapse.toml`
- `src/app_catalog/catalog/legacy_experimental/uptime-kuma.yaml`
- `src/app_catalog/catalog/mattermost.toml`
- `src/app_catalog/catalog/minio.yaml`
- `src/app_catalog/catalog/n8n-with-postgres-and-worker.yaml`
- `src/app_catalog/catalog/postgresql.yaml`
- `src/app_catalog/catalog/redis.yaml`
- `src/app_catalog/catalog/synapse-mysql-mariadb.toml`
- `src/app_catalog/catalog/synapse.toml`
- `src/app_catalog/catalog/uptime-kuma.yaml`

## Explicit exclusions

Django migration modules, test modules, package `__init__.py` files, generated catalog JSON reports, templates/static assets, bytecode/cache artifacts, and backup files such as `.bak` are excluded as independent documentation surfaces because they do not define independent production architecture contracts. Compatibility modules are **not** automatically excluded; they must be mapped and documented.

## Verification record

| Check | Evidence | Status |
|---|---|---|
| Installed app inventory | `src/config/settings.py` | source-derived |
| Production module inventory | recursive source-tree scan | source-derived |
| Models/fields | Python AST | validator-enforced |
| Serializers | Python AST | validator-enforced |
| HTTP/WebSocket surfaces | URL/routing/consumer source | validator-enforced |
| Celery tasks/schedules | task/configuration source | validator-enforced |
| Admin/Wagtail surfaces | registration source | validator-enforced |
| JSONFields | model AST | validator-enforced |
| Markdown artifacts/links | documentation scan | validator-enforced |
| Old deployment manual | repository path check | validator-enforced |

## Maintenance rule

A source change that adds a production surface must update its owning documentation or add a justified explicit exclusion. CI is source-derived so a hand-written checklist cannot silently drift from the repository.


## Wagtail administration coverage

The complete source-derived Wagtail ownership and coverage audit is maintained at [reference/wagtail-admin-audit.md](../reference/wagtail-admin-audit.md). It documents the intentional exposure decision for every concrete first-party model, editable versus read-only surfaces, domain actions, secrets handling, permissions, cross-app operator workflows and remaining dashboard candidates.

## 2026-10-01 maintenance additions

The source-derived validator excludes test modules (`tests.py`, `test_*.py`, `tests_*.py`) from production-surface coverage. The following production surfaces were added after the previous manifest baseline and are intentionally mapped to their owning app boundary:

### users
- `users.ProfileImagerSerializer`
- `users.DeletePasswordSerializer`

### auth_users
- `src/auth_users/tasks.py`

### services
- `src/services/wagtail_admin/views.py`

### deployments
- `src/deployments/core/docker_source.py`
- `src/deployments/core/routing.py`

### app_catalog
- `src/app_catalog/wagtail_admin/models.py`
- `src/app_catalog/wagtail_admin/views.py`
- `src/app_catalog/wagtail_hooks.py`

### custom_emails
- `custom_emails.EmailTemplateSerializer`
- `custom_emails.EmailTemplatePreviewSerializer`
- `custom_emails.EmailLogSerializer`

### plans
- Test modules are excluded by the validator and require no production-surface entry.
