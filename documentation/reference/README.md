# Engineering documentation reference

This directory contains source-aligned navigation and cross-app contract indexes.

## Start here

- [Backend API contracts](api-contracts.md) — API layers, ownership, authentication and main request flows.
- [Canonical source contract inventory](contracts.md) — one standardized table set for API routes, router registrations, models and fields.
- [API rate limiting](rate-limiting.md) — global, authentication and high-cost endpoint abuse-prevention policy.
- [Global contract coverage test](../../scripts/validate_documentation_contracts.py) — compares that inventory against source in CI.
- [Model field reference](model-field-reference.md) — field-by-field navigation across first-party models.
- [Documentation completeness](documentation-completeness.md) — source-derived documentation coverage policy.
- [Django/Wagtail admin audit](wagtail-admin-audit.md) — operator/admin exposure decisions.
- [Project layout](project-layout.md) — repository structure.

## Detailed API references

| Area | Reference |
|---|---|
| services | [services/api-reference.md](../apps/services/api-reference.md) |
| deployments | [deployments execution](../apps/deployments/execution/README.md) |
| deploy | [deploy/api-reference.md](../apps/deploy/api-reference.md) |
| auth_users | [auth_users/api-reference.md](../apps/auth_users/api-reference.md) |
| app_catalog / Ready Apps | [app_catalog/api-reference.md](../apps/app_catalog/api-reference.md) |
| Agent | [agent/api.md](../apps/agent/api.md) |
| Messenger | [messenger/api-reference.md](../apps/messenger/api-reference.md) |
| users | [users/api-reference.md](../apps/users/api-reference.md) |
| tickets | [tickets/api-reference.md](../apps/tickets/api-reference.md) |
| custom_emails | [custom_emails/api-reference.md](../apps/custom_emails/api-reference.md) |
| logs | [logs/api.md](../apps/logs/api.md) |
| docs | [docs/api.md](../apps/docs/api.md) |
| cms | [cms/api.md](../apps/cms/api.md) |

## Documentation rule

Source code remains authoritative. These references are intended to explain current behavior and prevent drift; they do not replace serializers, model validation, migrations, or runtime contracts.

Where an endpoint delegates to another domain boundary, the delegated serializer/service is the final requiredness contract. Documentation must not invent a required field that the source does not require.
