# core

## Purpose

core provides shared Django infrastructure: operator settings, cache namespaces, protected media, rendering/error adapters, metrics, throttling and common utilities.

## Why this boundary exists

These mechanisms are cross-cutting and would otherwise be duplicated across domain apps. core provides them without taking ownership of Service, authentication, messaging or ticket business state.

## Responsibilities

SystemSetting/CoreSettings and settings_service; app-cache helpers; protected media; global render/error behavior; throttling/metrics; shared email/ZIP utilities; Wagtail/cache admin diagnostics.

## Non-responsibilities

core must not own Service desired state, deployment execution, user authentication protocol, ticket access or messenger state. Cache is never durable authority.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [background.md](background.md)

## Security

System settings are admin-only; secret metadata is not a substitute for secure storage. Protected media validates path prefixes/traversal and the applicable credential/session.

## Invariants

1. Operator settings are not tenant configuration.
2. Cache loss must not lose durable domain state.
3. Protected media enforces authorization at the serving boundary.
4. Cross-cutting helpers must not become hidden business-domain owners.

## Reading order

models.md -> api.md -> background.md -> consuming app documentation.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)
