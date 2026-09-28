# PassDeployer Documentation

This directory is the canonical engineering documentation for the repository. The product documentation application at src/docs/ is separate application data.

## Start here

- [System architecture](architecture.md) — cross-app and control-plane overview.
- [Application architecture map](apps/README.md) — canonical Django app boundaries and problem navigation.
- [Control plane](control-plane.md) — HTTP/Celery/runtime flow.
- [Installation](installation.md), [Development](development.md), [Configuration](configuration.md).

## Django applications

Every first-party Django application has a canonical architectural entry point under [apps/](apps/):

- [users](apps/users/README.md)
- [auth_users](apps/auth_users/README.md)
- [services](apps/services/README.md)
- [plans](apps/plans/README.md)
- [deploy](apps/deploy/README.md)
- [deployments](apps/deployments/README.md)
- [logs](apps/logs/README.md)
- [app_catalog](apps/app_catalog/README.md)
- [messenger](apps/messenger/README.md)
- [tickets](apps/tickets/README.md)
- [custom_emails](apps/custom_emails/README.md)
- [docs](apps/docs/README.md)
- [core](apps/core/README.md)
- [cms](apps/cms/README.md)

Read the app README before changing that app. Follow its models/api/serializers/background/tests links according to the task.

## Deep deployments architecture

[deployments/README.md](deployments/README.md) remains the canonical execution manual for the deployment engine. It covers planning, build/platform detection, runtime/Swarm, concurrency/state, recovery, base images, logs/health/rollback/cleanup, databases and architectural tests.

The per-app deployments README points here rather than duplicating that manual.

- [Source-derived coverage manifest](apps/COVERAGE.md)\n\n## Cross-system operations

- [Observability](observability.md)
- [Testing and security](testing-and-security.md)
- [Project layout](reference/project-layout.md)

## Documentation authority

One architectural fact has one canonical home:

- system architecture: architecture.md
- cross-app architecture: apps/README.md
- app architecture: apps/<app>/README.md
- app model semantics: apps/<app>/models.md
- app HTTP API: apps/<app>/api.md
- app serializer contracts: apps/<app>/serializers.md
- app background/realtime behavior: apps/<app>/background.md when present
- app contract tests: apps/<app>/tests.md when present
- deep deployment execution: deployments/

When implementation changes, update the owning canonical document and then repair dependent links/claims. Do not restore deleted historical audits as competing sources of truth.
