# auth_users

## Responsibility
Authentication, OTP validation, JWT issuance/refresh/verification, password recovery and invite management.

Mounted below /auth/.

## API
GET /auth/api/settings/
POST /auth/api/authentication/
POST /auth/api/login/validate/
POST /auth/api/login/token/
POST /auth/api/set-password/
POST /auth/api/recovery/request/
POST /auth/api/recovery/confirm/
POST /auth/api/password-recovery/request/
POST /auth/api/password-recovery/confirm/
POST /auth/api/invite/validate/
POST /auth/api/invite/create/
GET /auth/api/invite/list/
POST /auth/api/invite/deactivate/
POST /auth/api/login/token/refresh
POST /auth/api/login/token/refresh/
POST /auth/api/login/token/verify
POST /auth/api/login/token/verify/
POST /auth/api/login/ (legacy)
POST /auth/api/signup/ (legacy)

## Admin
GET /auth/api/admin/login-settings/
GET /auth/api/admin/auth-codes/
DELETE /auth/api/admin/auth-codes/<int:pk>/
POST /auth/api/admin/auth-codes/purge/
GET /auth/api/validateToken/
