# auth_users models

This is the canonical model contract for auth_users. Field tables describe the current Django declarations; model notes explain architectural meaning beyond ORM metadata.

## LoginSettings

Singleton-like active authentication policy. save() validates policy and deactivates other rows; get_solo() resolves the active policy. It is read by login, signup, recovery and OTP logic.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| allow_username | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| allow_email | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| allow_phone | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| require_password | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| require_otp | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| password_as_second_factor | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| allow_auto_signup | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| auto_activate_on_signup | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|F\\|a\\|l\\|s\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| require_password_on_signup | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| activate_after_successful_otp | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| require_invite_for_signup | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|F\\|a\\|l\\|s\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| allow_username_recovery | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| recovery_via_email | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| recovery_via_phone | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| allow_password_recovery | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| password_recovery_via_email | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| password_recovery_via_phone | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| require_confirm_password | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| min_password_length | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|6\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| allow_login | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| custom_login_closed_message | TextField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| custom_login_closed_title | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|L\\|o\\|g\\|i\\|n\\| \\|t\\|e\\|m\\|p\\|o\\|r\\|a\\|r\\|i\\|l\\|y\\| \\|u\\|n\\|a\\|v\\|a\\|i\\|l\\|a\\|b\\|l\\|e\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| otp_length | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|8\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| otp_expire_minutes | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|5\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| otp_max_attempts | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|5\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| max_active_sessions | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|5\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| session_eviction_policy | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|S\\|e\\|s\\|s\\|i\\|o\\|n\\|E\\|v\\|i\\|c\\|t\\|i\\|o\\|n\\|P\\|o\\|l\\|i\\|c\\|y\\|.\\|R\\|E\\|V\\|O\\|K\\|E\\|_\\|O\\|L\\|D\\|E\\|S\\|T\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| is_active | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Boolean policy/state flag. Written by the owning workflow or admin boundary; consumers use it as authorization or lifecycle state, not as a substitute for an independent state machine. |
| updated_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## Device

A revocable client/device identity. UserSession points to it; revoked_at disables the device and therefore its sessions.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| public_id | UUIDField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|u\\|u\\|i\\|d\\|.\\|u\\|u\\|i\\|d\\|4\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Stable model identity; generated by the model layer. Readers use it as the durable object key; it is not business state and should not be repurposed. |
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| name | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Human-facing/domain identifier text. Written through the app's validated API/admin paths and read by UI/search; uniqueness/normalization rules must be preserved. |
| platform | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| client | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user_agent | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| last_ip | GenericIPAddressField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| last_seen_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| revoked_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## UserSession

Authoritative server-side session record for session-bound JWTs. Redis can cache it, but revocation/expiry/device state comes from this record.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| session_id | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| device | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| credential_hash | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| last_seen_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| expires_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| revoked_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| auth_generation | PositiveIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|1\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| last_ip | GenericIPAddressField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user_agent | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| metadata | JSONField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|d\\|i\\|c\\|t\\| | Structured JSON contract rather than an opaque blob. Its producer/consumer and snapshot/derived semantics are defined in the app documentation; arbitrary undocumented keys must not become API contracts. |

## UserContactChange

Pending/verified/cancelled contact-change transaction. User.email/phone is not changed until verification commits.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| public_id | UUIDField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|u\\|u\\|i\\|d\\|.\\|u\\|u\\|i\\|d\\|4\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Stable model identity; generated by the model layer. Readers use it as the durable object key; it is not business state and should not be repurposed. |
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| field | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| old_value | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| new_value | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| status | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|S\\|t\\|a\\|t\\|u\\|s\\|.\\|P\\|E\\|N\\|D\\|I\\|N\\|G\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| requested_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| verified_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| cancelled_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| requested_ip | GenericIPAddressField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user_agent | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |

## InviteLink

Cryptographically generated signup capability with use/expiry policy. uses_count is mutable consumption accounting, not identity.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| token | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|g\\|e\\|n\\|e\\|r\\|a\\|t\\|e\\|_\\|i\\|n\\|v\\|i\\|t\\|e\\|_\\|t\\|o\\|k\\|e\\|n\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Security-sensitive credential/reference. Written only by an authorized security workflow; raw values must not appear in ordinary read APIs. |
| label | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| created_by | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| max_uses | PositiveIntegerField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| uses_count | PositiveIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|0\\| | Derived/accounting counter. Treat as cached/ledger-like state and update through the owning operation, not arbitrary form input. |
| is_active | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Boolean policy/state flag. Written by the owning workflow or admin boundary; consumers use it as authorization or lifecycle state, not as a substitute for an independent state machine. |
| expires_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| updated_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## InviteUsage

Per-invite/per-user consumption record preventing the same user from consuming one invite repeatedly.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| invite | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| used_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| ip_address | GenericIPAddressField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user_agent | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |

## AuthCode

Short-lived, purpose-scoped one-time credential. attempts/expiry/consume form its state machine.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| contact | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| purpose | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|P\\|U\\|R\\|P\\|O\\|S\\|E\\|_\\|L\\|O\\|G\\|I\\|N\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| code | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|g\\|e\\|t\\|_\\|r\\|a\\|n\\|d\\|o\\|m\\|_\\|c\\|o\\|d\\|e\\|_\\|8\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| attempts | PositiveSmallIntegerField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|0\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| updated_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## LoginLog

Audit record of authentication events. It is intentionally best-effort so audit failure does not break login.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| user | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Ownership relation to the canonical users.User. Resource authorization normally starts from this relation. |
| username | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| identifier | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| event | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|E\\|V\\|E\\|N\\|T\\|_\\|S\\|U\\|C\\|C\\|E\\|S\\|S\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| method | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|M\\|E\\|T\\|H\\|O\\|D\\|_\\|O\\|T\\|H\\|E\\|R\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| success | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| ip_address | GenericIPAddressField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| user_agent | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| failure_reason | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| extra | JSONField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|d\\|i\\|c\\|t\\| | Structured JSON contract rather than an opaque blob. Its producer/consumer and snapshot/derived semantics are defined in the app documentation; arbitrary undocumented keys must not become API contracts. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## State, deletion and maintenance rules

The source model definitions call full_clean() on several important saves and define database constraints/indexes in Meta. Deletion behavior is part of the domain contract: read the on_delete declarations above together with the app README before changing cascades, SET_NULL, PROTECT or replacement semantics.

JSON fields are structured contracts. Do not introduce keys by observation from one API response; update the producer, consumer and serializer contract together. Sensitive JSON values are security state and must be redacted or encrypted according to the app rules.

## Implementation versus intent

**Current implementation:** the tables reflect the current master branch model declarations and call-site semantics.

**Architectural intent:** models store durable domain state; runtime observations and transient worker state are separated where the architecture requires it.

**Compatibility behavior:** fields explicitly described as projections, legacy state, or migration bridges must not be interpreted as a second source of truth.

**Do not assume:** a Django field being writable at the ORM level means any API or worker is allowed to mutate it. Workflow ownership and invariants in the app documentation control safe writes.
