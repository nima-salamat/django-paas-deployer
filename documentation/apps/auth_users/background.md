# auth_users background behavior

## OTP/authentication

OTP creation, validation and consumption are synchronous security operations; delivery may use asynchronous email infrastructure. AuthCode is purpose-scoped and attempt/expiry-limited.

## Session state

SessionJWTAuthentication resolves session-bound JWTs on every authenticated request. Session resolution may use Redis acceleration, but revocation/expiry/device state comes from UserSession.

Password reset and verified contact changes revoke existing sessions after the durable mutation commits.

## Admin maintenance

Expired/old AuthCode cleanup is an admin operation. Login logs record success/failure metadata without storing raw passwords or session credentials.

## Side effects

Authentication success can create Device/UserSession/LoginLog state and issue JWTs. Contact confirmation mutates User and revokes sessions with transaction.on_commit. These are security-sensitive cross-app side effects.

## Tests as contracts

auth_users/tests.py protects auth flow behavior; tests_sessions.py protects session-bound JWTs, logout/revocation and refresh behavior. When changing authentication, read both plus users.contact_api.
