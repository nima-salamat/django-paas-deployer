# auth_users API

App mount: /auth/. Routes below are relative to that mount.

Public login/recovery/invite operations use the authentication-free boundary required to start an auth flow; session/device/admin operations require authentication plus each view's admin/rule checks.

## Session/device routes

| Method | Route | Effect |
|---|---|---|
| GET | /api/sessions/ | Lists active sessions, including active_count, max_active_sessions, and session-management eligibility. |
| POST | /api/sessions/logout-all/ | Revokes all eligible sessions for the caller. |
| DELETE | /api/sessions/<session_id>/ | Revokes one session after verifying caller ownership. |
| GET | /api/devices/ | Lists caller-owned devices. |
| POST | /api/devices/<uuid:device_id>/sessions/ | Revokes sessions for a caller-owned device. |

## Login/authentication

| Method | Route | Effect |
|---|---|---|
| GET | /api/settings/ | Returns active login-policy configuration. |
| GET/POST | /api/admin/login-settings/ | Admin management of LoginSettings. |
| POST | /api/authentication/ | Starts the configured authentication flow and sends/records the required AuthCode. |
| POST | /api/login/validate/ | Validates the purpose-scoped OTP/auth code and advances the flow. |
| POST | /api/login/token/ | Completes authentication and creates/updates Device/UserSession state before issuing tokens. |
| POST | /api/set-password/ | Sets a password for an allowed account-setup flow. |

Legacy /api/login/ and /api/signup/ delegate into the same underlying flow.

## Recovery

- POST /api/recovery/request/ — request username recovery; unknown accounts use the anti-enumeration path.
- POST /api/recovery/confirm/ — consume recovery code and return the allowed recovery result.
- POST /api/password-recovery/request/ — start password reset.
- POST /api/password-recovery/confirm/ — consume reset code, update password/security state and issue resulting authentication state.

## Invite

- POST /api/invite/validate/ — validate active/expiry/use constraints.
- POST /api/invite/create/ — create an invite capability under the current admin policy.
- GET /api/invite/list/ — admin invite list/usage.
- POST /api/invite/deactivate/ — deactivate an invite.

## Auth-code administration

- GET /api/admin/auth-codes/ — admin list.
- POST /api/admin/auth-codes/purge/ — purge expired/old codes.
- DELETE /api/admin/auth-codes/<pk>/ — delete one code.

## Token compatibility

- GET/POST /api/validateToken/ — session-aware token validation; tokens without sid are rejected.
- POST /api/login/token/refresh and /api/login/token/refresh/ — session-bound refresh; tokens without sid are rejected.
- POST /api/login/token/verify and /api/login/token/verify/ — session-aware SimpleJWT verification; tokens without sid are rejected.

SessionTokenRefreshSerializer validates sid-bearing tokens against authoritative UserSession state, atomically rotates the stored refresh credential, rejects reuse of the previous refresh token, and refreshes the session cache after commit. The token verification endpoint applies the same session validity check for sid-bearing access tokens.

## WebSocket authentication

All first-party browser WebSockets authenticate with a session-bound access JWT supplied as the `token` query parameter. The handshake validates both the JWT and its `sid` against UserSession state. Live sockets revalidate that server-side session on heartbeat and close with application code `4401` after revocation. The browser is expected to refresh the access token and reconnect on `4401`; a temporary WebSocket close must not by itself clear a still-valid refresh session.

Current first-party endpoints:
- `/ws/messenger/`
- `/ws/tickets/`
- `/ws/tickets/notify/`
- `/ws/services/logs/<service_id>/`
- `/ws/services/shell/<service_id>/`
- `/ws/deployments/<deploy_id>/`

## Contact-change boundary

Contact-change routes are owned and registered by users.api_urls, not auth_users.urls:

- POST /api/users/user/contact-change/
- POST /api/users/user/contact-change/<uuid:change_id>/confirm/

They use auth_users.UserContactChange/AuthCode but mutate users.User only after verification. Read the users app docs for the complete transaction.

## Error/security contract

OTP and recovery flows are expiry/attempt bounded and anti-enumeration where configured. Authentication audit logging is best-effort. A revoked/expired Device or UserSession invalidates session-bound credentials.

Source: src/auth_users/urls.py, authentication.py, session_auth.py, token_serializers.py, api/*.py.