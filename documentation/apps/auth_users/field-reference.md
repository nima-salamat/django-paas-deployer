# auth_users — model field reference

This page is a source-derived reference of every Django model field declared in `src/auth_users/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/auth_users/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## LoginSettings

**Bases:** `models.Model`  
**Declared fields:** 29

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `allow_username` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow username value required by LoginSettings for its BooleanField contract. |
| `allow_email` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow email value required by LoginSettings for its BooleanField contract. |
| `allow_phone` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow phone value required by LoginSettings for its BooleanField contract. |
| `require_password` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the require password value required by LoginSettings for its BooleanField contract. |
| `require_otp` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the require otp value required by LoginSettings for its BooleanField contract. |
| `password_as_second_factor` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the password as second factor value required by LoginSettings for its BooleanField contract. |
| `allow_auto_signup` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow auto signup value required by LoginSettings for its BooleanField contract. |
| `auto_activate_on_signup` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the auto activate on signup value required by LoginSettings for its BooleanField contract. |
| `require_password_on_signup` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the require password on signup value required by LoginSettings for its BooleanField contract. |
| `activate_after_successful_otp` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the activate after successful otp value required by LoginSettings for its BooleanField contract. |
| `require_invite_for_signup` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the require invite for signup value required by LoginSettings for its BooleanField contract. |
| `allow_username_recovery` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow username recovery value required by LoginSettings for its BooleanField contract. |
| `recovery_via_email` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the recovery via email value required by LoginSettings for its BooleanField contract. |
| `recovery_via_phone` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the recovery via phone value required by LoginSettings for its BooleanField contract. |
| `allow_password_recovery` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow password recovery value required by LoginSettings for its BooleanField contract. |
| `password_recovery_via_email` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the password recovery via email value required by LoginSettings for its BooleanField contract. |
| `password_recovery_via_phone` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the password recovery via phone value required by LoginSettings for its BooleanField contract. |
| `require_confirm_password` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the require confirm password value required by LoginSettings for its BooleanField contract. |
| `min_password_length` | `PositiveSmallIntegerField` | no | no | `6` | DB non-null, blank not allowed | Stores the min password length value required by LoginSettings for its PositiveSmallIntegerField contract. |
| `allow_login` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the allow login value required by LoginSettings for its BooleanField contract. |
| `custom_login_closed_message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a message or message history. |
| `custom_login_closed_title` | `CharField` | no | yes | `"Login temporarily unavailable"` | DB non-null, blank allowed | Stores the custom login closed title value required by LoginSettings for its CharField contract. |
| `otp_length` | `PositiveSmallIntegerField` | no | no | `8` | DB non-null, blank not allowed | Stores the otp length value required by LoginSettings for its PositiveSmallIntegerField contract. |
| `otp_expire_minutes` | `PositiveSmallIntegerField` | no | no | `5` | DB non-null, blank not allowed | Stores the otp expire minutes value required by LoginSettings for its PositiveSmallIntegerField contract. |
| `otp_max_attempts` | `PositiveSmallIntegerField` | no | no | `5` | DB non-null, blank not allowed | Stores the otp max attempts value required by LoginSettings for its PositiveSmallIntegerField contract. |
| `max_active_sessions` | `PositiveSmallIntegerField` | no | no | `5` | DB non-null, blank not allowed | Stores the max active sessions value required by LoginSettings for its PositiveSmallIntegerField contract. |
| `session_eviction_policy` | `CharField` | no | no | `SessionEvictionPolicy.REVOKE_OLDEST` | DB non-null, blank not allowed, choices | Stores the session eviction policy value required by LoginSettings for its CharField contract. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable flag. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `allow_username`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow username as an identifier.
- `allow_email`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow email as an identifier.
- `allow_phone`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow phone number as an identifier.
- `require_password`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: If True, password is required when the user has one set.
- `require_otp`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: If True, a one-time code (OTP) is required.
- `password_as_second_factor`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `allow_auto_signup`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `auto_activate_on_signup`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `require_password_on_signup`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: When creating a new user, force them to set a password.
- `activate_after_successful_otp`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: After a valid OTP, set is_active=True (and mark email/phone verified).
- `require_invite_for_signup`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `allow_username_recovery`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Enable .
- `recovery_via_email`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow username recovery by sending OTP to email.
- `recovery_via_phone`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow username recovery by sending OTP to phone.
- `allow_password_recovery`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Enable .
- `password_recovery_via_email`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow password reset by sending OTP to email.
- `password_recovery_via_phone`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Allow password reset by sending OTP to phone.
- `require_confirm_password`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Require .
- `min_password_length`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Minimum password length enforced on set/reset.
- `allow_login`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Master switch: if False, all login/signup is blocked and custom message is shown.
- `custom_login_closed_message`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Message shown on login page when allow_login=False. Supports plain text..
- `custom_login_closed_title`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Title shown when login is closed.
- `otp_length`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `otp_expire_minutes`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `otp_max_attempts`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Max wrong OTP attempts before code is invalidated.
- `max_active_sessions`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Maximum number of active authenticated sessions per user..
- `session_eviction_policy`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior. Help text: How a login behaves when the active-session limit is reached..
- `is_active`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Only one settings row should be active.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## Device

**Bases:** `models.Model`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `public_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stable public identifier exposed instead of the database primary key. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=auth_devices; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-readable or user-selected name used for identification and UI. |
| `platform` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the platform value required by Device for its CharField contract. |
| `client` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the client value required by Device for its CharField contract. |
| `user_agent` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with an Agent control-plane identity. |
| `last_ip` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last ip value required by Device for its GenericIPAddressField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `last_seen_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Most recent observation/activity timestamp. |
| `revoked_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Timestamp proving that access was explicitly revoked. |

### Field-level notes

- `public_id`: `UUIDField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `platform`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `client`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `user_agent`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_ip`: `GenericIPAddressField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_seen_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `revoked_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.

## UserSession

**Bases:** `models.Model`  
**Declared fields:** 12

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `session_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique, indexed | Stores the session id value required by UserSession for its CharField contract. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=auth_sessions; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `device` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=sessions; on_delete=CASCADE | Stores the device value required by UserSession for its ForeignKey contract. |
| `credential_hash` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the credential hash value required by UserSession for its CharField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `last_seen_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Most recent observation/activity timestamp. |
| `expires_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Time after which the credential/session/invite is no longer valid. |
| `revoked_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Timestamp proving that access was explicitly revoked. |
| `auth_generation` | `PositiveIntegerField` | no | no | `1` | DB non-null, blank not allowed | Stores the auth generation value required by UserSession for its PositiveIntegerField contract. |
| `last_ip` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last ip value required by UserSession for its GenericIPAddressField contract. |
| `user_agent` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with an Agent control-plane identity. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `session_id`: `CharField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `device`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `credential_hash`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_seen_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `expires_at`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `revoked_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `auth_generation`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `last_ip`: `GenericIPAddressField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `user_agent`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## UserContactChange

**Bases:** `models.Model`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `public_id` | `UUIDField` | no | no | `uuid.uuid4` | DB non-null, blank not allowed, unique, indexed | Stable public identifier exposed instead of the database primary key. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=contact_changes; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `field` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed, choices | Stores the field value required by UserContactChange for its CharField contract. |
| `old_value` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the old value value required by UserContactChange for its CharField contract. |
| `new_value` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the new value value required by UserContactChange for its CharField contract. |
| `status` | `CharField` | no | no | `Status.PENDING` | DB non-null, blank not allowed, indexed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `requested_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the requested at value required by UserContactChange for its DateTimeField contract. |
| `verified_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the verified at value required by UserContactChange for its DateTimeField contract. |
| `cancelled_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the cancelled at value required by UserContactChange for its DateTimeField contract. |
| `requested_ip` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the requested ip value required by UserContactChange for its GenericIPAddressField contract. |
| `user_agent` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with an Agent control-plane identity. |

### Field-level notes

- `public_id`: `UUIDField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `field`: `CharField` with DB non-null, blank not allowed, indexed, choices. The model declaration is authoritative for validation and persistence behavior.
- `old_value`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `new_value`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, indexed, choices. The model declaration is authoritative for validation and persistence behavior.
- `requested_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `verified_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cancelled_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `requested_ip`: `GenericIPAddressField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `user_agent`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## InviteLink

**Bases:** `models.Model`  
**Declared fields:** 9

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `token` | `CharField` | no | no | `generate_invite_token` | DB non-null, blank not allowed, unique, indexed | Stores the token value required by InviteLink for its CharField contract. |
| `label` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the label value required by InviteLink for its CharField contract. |
| `created_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=created_invites; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `max_uses` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the max uses value required by InviteLink for its PositiveIntegerField contract. |
| `uses_count` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the uses count value required by InviteLink for its PositiveIntegerField contract. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable flag. |
| `expires_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Time after which the credential/session/invite is no longer valid. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `token`: `CharField` with DB non-null, blank not allowed, unique, indexed. The model declaration is authoritative for validation and persistence behavior.
- `label`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Optional internal note (e.g. .
- `created_by`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `max_uses`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Maximum number of successful signups. Leave empty for unlimited..
- `uses_count`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `is_active`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `expires_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Optional expiry datetime. Leave empty for no expiry..
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## InviteUsage

**Bases:** `models.Model`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `invite` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=usages; on_delete=CASCADE | Stores the invite value required by InviteUsage for its ForeignKey contract. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=invite_usages; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `used_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Stores the used at value required by InviteUsage for its DateTimeField contract. |
| `ip_address` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the ip address value required by InviteUsage for its GenericIPAddressField contract. |
| `user_agent` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with an Agent control-plane identity. |

### Field-level notes

- `invite`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `used_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `ip_address`: `GenericIPAddressField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `user_agent`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## AuthCode

**Bases:** `models.Model`  
**Declared fields:** 7

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `user` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=auth_codes; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `contact` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the contact value required by AuthCode for its CharField contract. |
| `purpose` | `CharField` | no | no | `PURPOSE_LOGIN` | DB non-null, blank not allowed, choices | Stores the purpose value required by AuthCode for its CharField contract. |
| `code` | `CharField` | no | no | `get_random_code_8` | DB non-null, blank not allowed | Stores the code value required by AuthCode for its CharField contract. |
| `attempts` | `PositiveSmallIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the attempts value required by AuthCode for its PositiveSmallIntegerField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp used for history, ordering and auditing. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last mutation timestamp used for ordering and cache/reconciliation decisions. |

### Field-level notes

- `user`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior. Help text: Null only for recovery when we only know email/phone.
- `contact`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Email or phone used when user is not yet resolved (recovery).
- `purpose`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `code`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `attempts`: `PositiveSmallIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `updated_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## LoginLog

**Bases:** `models.Model`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `user` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=login_logs; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `username` | `CharField` | no | yes | `""` | DB non-null, blank allowed, indexed | Stores the username value required by LoginLog for its CharField contract. |
| `identifier` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the identifier value required by LoginLog for its CharField contract. |
| `event` | `CharField` | no | no | `EVENT_SUCCESS` | DB non-null, blank not allowed, indexed, choices | Stores the event value required by LoginLog for its CharField contract. |
| `method` | `CharField` | no | no | `METHOD_OTHER` | DB non-null, blank not allowed, choices | Stores the method value required by LoginLog for its CharField contract. |
| `success` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed, indexed | Stores the success value required by LoginLog for its BooleanField contract. |
| `ip_address` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the ip address value required by LoginLog for its GenericIPAddressField contract. |
| `user_agent` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with an Agent control-plane identity. |
| `failure_reason` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the failure reason value required by LoginLog for its CharField contract. |
| `extra` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the extra value required by LoginLog for its JSONField contract. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Creation timestamp used for history, ordering and auditing. |

### Field-level notes

- `user`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `username`: `CharField` with DB non-null, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `identifier`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior. Help text: Email / phone / username used at login time.
- `event`: `CharField` with DB non-null, blank not allowed, indexed, choices. The model declaration is authoritative for validation and persistence behavior.
- `method`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `success`: `BooleanField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `ip_address`: `GenericIPAddressField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `user_agent`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `failure_reason`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `extra`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_at`: `DateTimeField` with DB non-null, blank not allowed, indexed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
