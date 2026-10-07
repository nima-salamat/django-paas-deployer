# users

## Purpose

users owns canonical identity, account presentation, roles/permissions, profile assets and balance/account records.

## Why this boundary exists

Every domain needs one durable user principal for ownership and authorization. Authentication has a separate lifecycle and belongs to auth_users; users must remain the identity source.

## Responsibilities

Custom AUTH_USER_MODEL; profiles; account fields; staff/superuser flags; rule permissions; receipts/balance; user/admin APIs; identity-related cleanup.

## Non-responsibilities

OTP/session/authentication is auth_users. Service ownership is services. Runtime/deployment execution is deployments. Product docs is docs.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)
- [tests.md](tests.md)

## Security

Resource-owning apps enforce ownership; users supplies the identity/role facts. Direct email/phone changes are rejected and must use verified contact-change flow.

## Invariants

1. AUTH_USER_MODEL is users.User.
2. Authentication state is not identity state.
3. Profile storage is user-owned.
4. Account balance changes are transactional.
5. User deletion must follow cleanup side effects.

## Reading order

models.md -> serializers.md -> api.md -> background.md -> tests.md. Read ../auth_users/README.md for credential/session flows.


## Wagtail administration

The canonical user editor is Wagtail's built-in **Settings → Users** surface using the project's custom user forms. `Profile` remains editable. `Receipt` is read-only in Wagtail; payment mutation remains in Django Admin. `Rule` is now read-only in Wagtail because its values are used as staff capability grants by other applications.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)
