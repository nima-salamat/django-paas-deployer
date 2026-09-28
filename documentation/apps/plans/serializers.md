# plans serializers

## PlanSerializer

ModelSerializer exposing all Plan model fields. id, created_at and updated_at are read-only. It is used by admin or trusted/internal representations, not a substitute for public authorization.

## UnauthorizedPlanSerializer

Public/narrow Plan representation containing identity, platform, resource ceilings, storage type, plan type and pricing. The name reflects the public representation; it does not mean unauthenticated callers automatically gain access to every plan management operation.

## Sensitive dependencies

Plan fields are policy inputs consumed by Services and deployment planning. A serializer change that adds a writable policy field must be followed into the API/view permission and the consumer enforcing that policy.

Source: src/plans/serializers.py.
