# custom_emails

## Purpose

custom_emails owns admin-defined email templates, durable delivery records and asynchronous external email delivery.

## Why this boundary exists

Template/configuration changes and external delivery have different failure modes. EmailLog makes the intent durable so Celery can retry without coupling HTTP requests to the provider.

## Responsibilities

Template CRUD/preview; recipient validation; rendering/sanitization; EmailLog persistence; Celery delivery/retry; administrative statistics/retry/search.

## Non-responsibilities

OTP/auth flow policy belongs to auth_users even if it uses the same email transport. Resend credentials/proxy settings are core/operator configuration.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)

## Security

Current HTTP management is superuser-only. Header injection is rejected; rendered HTML is sanitized; delivery credentials never enter serializer/API contracts.

## Invariants

1. HTTP creates durable EmailLog intent; Celery performs the external send.
2. SENT is idempotent against duplicate task delivery.
3. Failed delivery is explicit before retry.
4. Completed history is not rewritten when a template changes.

## Reading order

models.md -> serializers.md -> api.md -> background.md.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)

## Detailed contracts

- [Detailed API reference](api-reference.md)
