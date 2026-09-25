# Authentication and Messenger Architecture Audit

Status: investigation baseline for `refactor/service-centric-runtime` (2026-09-25)

This document records the current implementation and the smallest safe direction for improving authentication and realtime messaging. It is deliberately a migration design, not a claim that the target architecture already exists.

## 1. Current authentication flow

The configured user model is `users.User` (`src/users/models.py`). It is an `AbstractBaseUser` with a username login field and optional email/phone identifiers. Authentication policy is stored in the singleton-style `auth_users.LoginSettings` model and is editable through the auth/Wagtail surfaces.

The current login flow is:

```text
POST /auth/api/authentication/
  -> StartAuthAPIView
  -> LoginSettings + identifier resolution
  -> optional user creation + AuthCode OTP

POST /auth/api/login/validate/
  -> ValidateOTPAPIView
  -> AuthCode.validate / user activation

POST /auth/api/login/token/
  -> FinalAuthAPIView
  -> OTP/password verification
  -> auth_users.services.get_tokens_for_user
  -> SimpleJWT RefreshToken.for_user
```

`SetPasswordAPIView` is a parallel completion path. Password recovery and legacy aliases are in `auth_users/api/recovery.py`, `auth_users/apis.py`, and `auth_users/urls.py`. Successful and failed attempts are written to `LoginLog`; raw OTP values are currently written by the SMS/email fallback logger and must be treated as a security issue before production use.

For HTTP APIs, `config.settings.REST_FRAMEWORK` configures `JWTAuthentication` globally. Several endpoints also declare `JWTAuthentication` directly, including most messenger APIs and protected media. Django session authentication is present only on selected control-plane APIs. There is no first-class application session record connecting a token, device, and revocation state.

The current token authority is therefore the signed JWT plus SimpleJWT's blacklist tables/configuration. A JWT can remain cryptographically valid after a security-sensitive event unless blacklist or another server-side check catches it.

## 2. Current WebSocket flow

`config/asgi.py` wraps all websocket routes in `channels.auth.AuthMiddlewareStack`, but `messenger.consumers.authenticate_from_scope()` independently parses `?token=` and constructs `rest_framework_simplejwt.tokens.AccessToken`. It then queries `users.User` and checks `is_active`. The messenger consumer does not resolve a server-side session, device, refresh credential, or revocation record.

The same direct JWT parsing pattern exists in `services.consumers` for service logs and shell, and protected media manually parses either a bearer token or query token. Introducing session authority must therefore be compatible with these consumers rather than changing only the messenger connection.

## 3. Current messenger flow

Persistent state is in PostgreSQL models in `src/messenger/models.py`:

```text
Conversation
  -> ConversationParticipant
  -> Message
       -> MessageReaction / MessageReadReceipt / MessageAttachment
  -> PinnedMessage / JoinRequest / GroupInviteLink
CallSession
  -> CallSessionParticipant
```

The HTTP API is feature-split under `src/messenger/api/` but retains `messenger/apis.py` as a compatibility re-export. Important paths include:

```text
POST /messenger/conversations/{id}/messages/
  -> MessageListCreateAPIView
  -> membership and send-policy checks
  -> Message.objects.create (+ attachments)
  -> message cache scheduling
  -> consumers.broadcast_message
  -> Channels group fan-out
```

Message listing correctly treats PostgreSQL as the fallback/source of truth and uses a bounded Redis hot-window through `message_cache.py`. However, message creation broadcasts inside the request loop rather than publishing a durable event after commit, and there is no client idempotency key or unique operation record. A WebSocket send is consequently delivery fan-out, not proof of durable delivery.

`MessengerConsumer` owns authentication, presence bookkeeping, conversation subscription, typing, drafts, and transport events. Presence and connection counts are ephemeral cache keys. Calls are persisted as `CallSession`, but call signaling and broadcast behavior are spread between `api/calls.py` and the consumer helper functions; the model's status choices (`ringing`, `active`, `ended`, `missed`, `declined`, `no_answer`) are not yet a complete transition service.

## 4. Concrete weaknesses

### Authentication

* No persistent `UserSession` or `Device` authority exists.
* WebSocket, media, service-log, and HTTP authentication have separate token parsing paths.
* Query-string tokens are accepted for WebSockets and media, increasing accidental leakage risk through logs, browser history, and referrers.
* Session limits, device logout, logout-all, and revocation APIs do not exist as a coherent application service.
* Login completion calls token creation directly from presentation code.
* Redis is not currently used for authentication context; adding it must not make Redis authoritative.
* Password reset and security-sensitive account changes do not have a single session invalidation policy.
* Login/OTP policy is database-backed, but its mutation and login flow are not one explicit session-creation transaction.

### Messenger

* HTTP views contain substantial domain rules and call transport helpers directly.
* `broadcast_message` and related helpers are an infrastructure API exposed to many feature views.
* Message persistence, cache mutation, and fan-out are not consistently ordered with `transaction.on_commit`.
* Duplicate message submission has no durable idempotency boundary.
* Redis message caching is useful acceleration, but synchronization after reconnect is based on message pagination rather than a durable event cursor.
* `last_read_at` plus per-message receipt rows mix summary and detailed read state without a single application service.
* Presence/typing are correctly ephemeral in principle, but the consumer is responsible for their policy, persistence calls, and transport.
* Attachment validation and authorization are distributed across media views, serializers, and utility functions.
* Call state is persisted, but transition validation and signaling transport are coupled in API code.
* Several endpoints explicitly select JWT authentication, making a future common session backend easy to bypass accidentally.

## 5. Configuration and ownership map

| Concern | Current source | Intended scope/owner | Mutable without restart? | Secret? |
|---|---|---|---|---|
| Identifier/OTP/login policy | `auth_users.LoginSettings` | platform auth policy / operator | yes | no |
| Password hashing | Django `User` + Django auth | platform infrastructure | code/config | no |
| JWT lifetimes/algorithm | `config.settings.SIMPLE_JWT` | bootstrap security configuration | usually restart | signing key is secret |
| JWT signing key | `SECRET_KEY` environment | process infrastructure | restart/rotation | yes |
| Database/cache endpoints | environment/settings | process infrastructure | restart | credentials are secret |
| User identity | `users.User` | account domain | yes | password hash is sensitive |
| Device identity | absent | client-generated opaque ID + auth domain | yes | identifier is sensitive metadata |
| Authenticated session | absent | database `UserSession` | yes | credential hash only |
| Session cache | absent | Redis acceleration | runtime | must exclude credentials |
| Conversation/membership | messenger models | messenger domain | yes | no |
| Message/call history | messenger models | durable messenger domain | yes | message content may be private |
| Presence/typing/connection | Redis/channel layer | ephemeral realtime infrastructure | runtime | no |
| Attachment bytes | configured storage | storage infrastructure, guarded by domain auth | runtime | private media is sensitive |
| Jitsi/other call configuration | `api/calls.py` + settings/env | platform call policy/runtime adapter | policy-dependent | room/auth values may be sensitive |

The migration should not move infrastructure endpoints or signing keys into Wagtail. Wagtail may manage operator policy (session limits, whether login is open, retention, supported call mode), while process startup owns credentials and network endpoints.

## 6. Target authentication model

Introduce two models in `auth_users`:

```text
Device
  user, public_id, platform, client_name, user_agent, last_ip,
  created_at, last_seen_at, revoked_at

UserSession
  user, device, session_id, credential_hash, created_at,
  last_seen_at, expires_at, revoked_at, auth_generation, metadata
```

`session_id` is an opaque random identifier suitable for a token claim. The database stores a hash/fingerprint of any refresh/session credential, never a raw access or refresh token. A session is the revocable server-side authority; a short-lived JWT is a transport credential carrying the session identifier and user identifier. Existing JWTs remain accepted during migration through a compatibility path, but new sessions are created for the new login completion path.

The first implementation should use one deterministic policy: configurable maximum active sessions per user, with `REVOKE_OLDEST` as the default migration-compatible eviction behavior. Add `REJECT_NEW` only if an operator requirement exists. Enforce the limit inside `transaction.atomic()` while locking the user's active session rows; the database remains the final authority under concurrent logins.

## 7. Session cache and authentication contract

Use a compact immutable cache value:

```text
auth:session:<session_id> -> {
  session_id, user_id, device_id, auth_generation,
  expires_at, revoked: false
}
```

The TTL must not exceed `expires_at`. Cache misses read PostgreSQL and repopulate the value. Redis failures use an explicit safe fallback: consult PostgreSQL rather than authenticating from stale cache; if the database is unavailable, reject authentication rather than silently accepting an unverifiable session. Revocation updates the row and deletes the cache key. A generation/version check handles password reset and other account-wide invalidations without scanning every cached request.

Create one `SessionAuthenticationService` used by DRF authentication, WebSocket scope authentication, media, service logs, and shell. It should return an `AuthenticatedSessionContext` and optionally resolve the user; callers must not parse JWTs independently. During migration, a legacy token resolver can validate a JWT and produce a compatibility context with no session row, while new tokens always carry the session identifier.

## 8. Target messenger architecture

```text
HTTP / WebSocket
       -> authenticated session context
       -> Messenger application commands
       -> domain authorization + transaction
       -> PostgreSQL durable state
       -> on-commit event publisher
       -> Redis/Channels fan-out
       -> reconnect synchronization from PostgreSQL
```

The domain/application boundary should contain conversation membership, message creation/edit/delete, idempotency, read state, attachment association, and call transitions. HTTP and WebSocket are transports only.

Add a durable `MessengerEvent` (or equivalent outbox) only when implementation reaches event publication. It should include `event_id`, event type, conversation, actor, message/call reference, created time, and JSON payload with no secrets. A client cursor can then synchronize events after reconnect; message pagination remains available as a bounded recovery path. Publish only after commit, and make publication retryable/idempotent.

For message submission, accept a client-generated idempotency key scoped to sender/conversation. Store it with a unique constraint and return the original message on a retry. Existing rows remain valid because the new field is nullable during migration.

Keep presence, typing, connection heartbeat, and transient call signaling in Redis/Channels. Keep conversations, members, messages, read state, attachments, and the minimum auditable call lifecycle in PostgreSQL.

## 9. Calls

Introduce a call transition service around existing `CallSession`. The transport may carry WebRTC/Jitsi signaling, but it cannot infer authoritative state. Validate transitions such as `RINGING -> ACTIVE -> ENDED`, `RINGING -> DECLINED/MISSED/CANCELLED`, and reject or safely ignore duplicate terminal events. Use database row locks for competing join/end operations and publish call events after commit.

## 10. API direction

Add session management endpoints without exposing credentials:

```text
GET    /auth/sessions/
DELETE /auth/sessions/{id}/
POST   /auth/sessions/logout-all/
GET    /auth/devices/
DELETE /auth/devices/{id}/sessions/
```

Preserve existing auth routes and messenger routes. New application services should be called by both existing API views and WebSocket handlers. Error responses remain the existing structured JSON contract while adding stable machine-readable codes where the endpoint is touched.

## 11. Migration strategy

1. Add nullable/session tables and indexes; do not rewrite users, messages, or calls.
2. Add token/session service and tests while retaining legacy JWT validation.
3. Make new login completion create a session and embed its opaque ID in access/refresh tokens.
4. Switch DRF and WebSocket authentication to the common resolver; preserve legacy-token fallback temporarily.
5. Add cache lookup/invalidation and session/device APIs/admin visibility.
6. Move messenger message creation behind an application command with idempotency and `on_commit` publication.
7. Add durable cursor/outbox only after the command path is stable.
8. Route call transitions through the state service.
9. Retire direct JWT parsing and compatibility paths only after integration evidence and a documented token migration window.

No existing message or call data should be deleted. Existing clients without a device ID receive a generated compatibility device at login; client-provided device metadata remains descriptive and is never an authority.

## 12. Security model

* Never log access tokens, refresh tokens, passwords, OTP values, session credentials, private attachment URLs, or call credentials.
* Prefer authorization headers for HTTP and a short-lived connection credential or handshake protocol for WebSockets; retain query-token compatibility only during a controlled migration.
* Namespace all cache keys and validate session/user binding on every lookup.
* Do not trust client platform, user-agent, or device labels as identity.
* Revoke current/device/all sessions explicitly and invalidate cache entries.
* Enforce conversation membership and attachment access server-side.
* Ensure account-wide security changes bump the auth generation.

## 13. Test matrix

### Authentication

Test login/session creation, device association, cache hit/miss, Redis failure fallback, expiry, logout/revocation, logout-all, device revocation, session-limit races, token replay after revocation, password-reset invalidation, DRF authentication, media authentication, service/shell authentication, and WebSocket authentication with revoked sessions.

### Messenger

Test conversation membership, message create/edit/delete/reply/reaction, duplicate idempotency requests, ordering, cursor/pagination, read/unread, attachment authorization and cleanup, blocking, presence/typing, reconnect synchronization, call transitions, duplicate call events, and revoked-session disconnect policy.

### Integration

Run PostgreSQL + Redis + Django + Channels through the complete flow:

```text
login -> UserSession -> authenticated HTTP -> authenticated WebSocket
      -> message command -> PostgreSQL commit -> Redis fan-out
      -> reconnect cursor -> session revocation -> rejected future connection
```

## 14. Implementation phases

1. Add session/device models, policy constants, migration, and pure session lifecycle tests.
2. Implement session issuance, hashing, cache adapter, invalidation, and a common authentication context.
3. Integrate login completion and DRF authentication with a legacy fallback.
4. Integrate WebSocket/media/service consumers and add session/device APIs plus admin visibility.
5. Extract messenger application commands and authorization from HTTP/consumer transport.
6. Add message idempotency and post-commit event publication.
7. Add durable synchronization/cursor support and improve read state/pagination.
8. Extract call state transitions and event publication.
9. Run real PostgreSQL/Redis/Channels tests, security review, and compatibility cleanup.

The first implementation commit should be limited to the session domain model and its tests. Messenger transport changes must wait until the common authentication contract is proven.

