# auth_users serializers

## SessionTokenRefreshSerializer

Purpose: bridge SimpleJWT refresh with server-side session revocation.

Input is the refresh token. Before parent refresh processing, the serializer extracts sid and user_id and resolves the corresponding UserSession. A token without sid is treated as a legacy compatibility JWT.

After successful refresh, the new refresh token hash replaces credential_hash on the still-valid session and last_seen_at is updated. A revoked/invalid/expired session raises AuthenticationFailed.

There are intentionally few DRF serializers in auth_users: many authentication APIs perform protocol validation directly because the flow is not ordinary model CRUD. Do not infer that absence of a serializer means absence of validation; inspect the flow module.

## Security contract

The serializer never returns the stored credential_hash. sid is an internal session correlation value, not an authorization scope.

API -> serializer -> session authority:

POST /api/login/token/refresh[slash]
 -> SessionTokenRefreshSerializer
 -> SimpleJWT refresh validation
 -> resolve_session(sid,user_id)
 -> update session credential hash/last_seen
 -> new tokens

Source: src/auth_users/token_serializers.py, authentication.py, session_auth.py.
