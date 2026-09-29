# auth_users background behavior

## OTP/authentication

OTP creation, validation and consumption are synchronous security operations; delivery may use asynchronous email infrastructure. AuthCode is purpose-scoped and attempt/expiry-limited.

## Session state

SessionJWTAuthentication resolves session-bound JWTs on every authenticated request. Redis is a bounded acceleration layer for UserSession lookups; PostgreSQL remains authoritative for session identity, expiry and revocation.

A newly issued session is populated into Redis immediately after the login transaction commits. The default session-cache lease is 15 minutes and is renewed on each successful cache hit without rewriting the cached session payload. Session last-seen timestamps are persisted on a bounded interval rather than on every API request.

Session revocation paths invalidate Redis only after the durable database transaction commits. This includes single-session revoke, logout-all, device revoke, automatic oldest-session eviction and Django Admin session/device actions.

Each user is limited by LoginSettings.max_active_sessions. When that ceiling is reached the configured eviction policy either revokes the oldest active sessions or rejects the new login.

Password reset and verified contact changes revoke existing sessions after the durable mutation commits.

## Admin maintenance

Expired/old AuthCode cleanup is an admin operation. Rotated SimpleJWT refresh tokens use the SimpleJWT blacklist app and expired blacklist records are purged daily by the authentication Celery task. Login logs record success/failure metadata without storing raw passwords or session credentials.

## Side effects

Authentication success can create Device/UserSession/LoginLog state and issue JWTs. Contact confirmation mutates User and revokes sessions with transaction.on_commit. These are security-sensitive cross-app side effects.

## Tests as contracts

auth_users/tests.py protects auth flow behavior; tests_sessions.py protects session-bound JWTs, logout/revocation and refresh behavior. When changing authentication, read both plus users.contact_api.
