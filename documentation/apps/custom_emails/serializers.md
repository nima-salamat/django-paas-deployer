# custom_emails serializers

The current serializers are compact because the main policy is enforced in APIs/services.

## EmailTemplate serializers

Template create/update serializers validate template identity, active state and template content used by the rendering service. Preview uses the same render/sanitize path without external delivery.

## EmailLog serializers

Email-log representations are read-oriented: delivery status, recipient/subject/timestamps and safe body preview are exposed. Raw provider responses and sensitive transport credentials are not a customer-facing contract.

## Sensitive fields

Recipient addresses and rendered content are operational data. Body previews are truncated by the persistence layer. Resend/API credentials belong to core/settings, not serializer input.

## Mapping

POST /send/ -> serializer/request validation -> EmailLog PENDING -> Celery delivery.

Source: src/custom_emails/serializers.py, apis.py, services.py.
