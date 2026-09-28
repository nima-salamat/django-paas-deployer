# auth_users

## Purpose

auth_users owns the authentication protocol and the durable security state needed to make credentials/session validity revocable and auditable.

## Why this boundary exists

Login policy, OTP attempts, recovery, device revocation and server-side sessions have different lifecycles from durable identity. users owns the User; auth_users owns the authentication state attached to that user.

## Responsibilities

LoginSettings; OTP/auth flows; signup/invite gating; recovery; contact-change verification; Device/UserSession; session-aware JWT authentication/refresh; LoginLog.

## Non-responsibilities

Canonical identity/profile is users. Resource authorization is owned by each domain. Service secrets are services. Email templates are custom_emails.

## Documents

- [models.md](models.md)
- [api.md](api.md)
- [serializers.md](serializers.md)
- [background.md](background.md)
- [tests.md](tests.md)

## Security boundary

Session-bound JWTs with sid are validated against UserSession on every authenticated request. Legacy JWTs without sid remain a compatibility path. OTPs are purpose-scoped and expiry/attempt limited. Contact changes mutate User only after destination verification.

## Invariants

1. users.User remains identity truth.
2. UserSession is authority for session-bound token validity.
3. Contact changes remain pending until verified.
4. Revocation must invalidate session-bound credentials.
5. AuthCode cannot be reused after consumption.

## Reading order

models.md -> api.md -> serializers.md -> background.md -> tests.md. Read ../users/README.md for identity ownership.


## Wagtail administration

Wagtail exposes login policy, invite-link metadata, invite usage and login audit metadata. `LoginSettings` remains a singleton: change is allowed but add/delete are blocked. Invite bearer tokens and OTP/auth codes are not exposed in Wagtail. Device/session/contact-change security workflows remain in Django Admin where existing revoke and verification semantics are implemented.
