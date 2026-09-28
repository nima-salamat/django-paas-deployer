# auth_users state and choice contracts

## AuthCode

Each code has a purpose and expiry/attempt lifecycle. Important purposes include login/OTP, recovery, password reset and contact change. A valid code is consumed once; invalid attempts increment the stored attempt state.

## UserSession

A session is valid only while not revoked/expired and while its associated Device is usable. sid-bearing JWTs are accepted only when this server-side state resolves successfully.

## UserContactChange

pending -> verified or cancelled. User.email/phone changes only when verification succeeds. Older pending changes are cancelled when a new change is requested.

## LoginSettings

Operator policy controls whether login/password recovery/username recovery and invitation gating are available. API flows consult the active settings row rather than hard-coding one public policy.
