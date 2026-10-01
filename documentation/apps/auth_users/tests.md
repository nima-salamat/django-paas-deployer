# auth_users contracts and tests

| Test | Protected behavior | Invariant |
|---|---|---|
| tests.py | login/OTP/recovery/auth compatibility | one-time credentials and auth flow states cannot be bypassed |
| tests_sessions.py | session-bound JWT/revocation/device handling | sid-bearing tokens require valid UserSession state |
| tests_sessions.py | legacy Redis session-cache payloads | cached session metadata, including cached_at, remains deserializable during rolling deployments |

Authentication changes must be tested across both legacy JWT tokens (without sid) and session-bound tokens. Contact-change changes also require users contact-change coverage because verification mutates User and revokes sessions.
