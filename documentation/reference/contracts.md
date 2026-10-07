# Source contract inventory

This file is the machine-checkable documentation index for first-party models and HTTP API routes.

**Generation rule:** every inventory row has a stable source signature. CI compares source declarations against these tables and fails when a model, declared field, explicit route, router registration, or router action is added/removed without updating this file.

The detailed app documentation remains the narrative contract. This file answers one narrower question: **does the documented contract inventory contain the thing that exists in source?**

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path |
|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `models.Model` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `models.Model` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `models.Model` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `Document` | `models.Model` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `models.Model` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `models.Model` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `models.Model` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `messenger` | `src/messenger/models.py` | `UserBio` | `models.Model` | [field reference](../apps/messenger/field-reference.md#userbio) |
| `messenger` | `src/messenger/models.py` | `Contact` | `models.Model` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `Block` | `models.Model` | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | `models.Model` | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | `models.Model` | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `models.Model` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `models.Model` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `models.Model` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `models.Model` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `Message` | `models.Model` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `models.Model` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `models.Model` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `models.Model` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `models.Model` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `action` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `certainty` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `credential` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `duration_ms` | `PositiveIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `error_code` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `failure_domain` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `http_status` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `occurred_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `request_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_effect` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `retryability` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `success` | `BooleanField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `visibility` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_ip` | `GenericIPAddressField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `revoked_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `issued_from_ip` | `GenericIPAddressField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `key` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `method` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `path` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `request_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `response_body` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `state` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `status_code` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `Agent` | `description` | `TextField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `disabled_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `name` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `provisioning_source` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `revoked_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `scopes` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `status` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agent) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `code` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `contact` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `purpose` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `client` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `name` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `platform` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_by` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `label` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `max_uses` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `token` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `uses_count` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `invite` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `used_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `event` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `extra` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `failure_reason` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `identifier` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `method` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `success` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `username` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `activate_after_successful_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_auto_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_login` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_password_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `auto_activate_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_message` | `TextField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_title` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `max_active_sessions` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `min_password_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_expire_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_max_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_as_second_factor` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_confirm_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_invite_for_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `session_eviction_policy` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `cancelled_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `field` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `new_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `old_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `status` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `verified_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `auth_generation` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `credential_hash` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `device` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `session_id` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `plans` | `src/plans/models.py` | `Plan` | `log_ingest_bytes_per_sec` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_quota_behavior` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_retention_days` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `log_storage_mb` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_cpu` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_ram` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `max_storage` | `PositiveIntegerField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `name` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `persistent_logging` | `BooleanField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `plan_type` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `platform` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `price_per_hour` | `FloatField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `realtime_logging` | `BooleanField` | [field reference](../apps/plans/field-reference.md#plan) |
| `plans` | `src/plans/models.py` | `Plan` | `storage_type` | `CharField` | [field reference](../apps/plans/field-reference.md#plan) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `database` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `password_ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `username` | `CharField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseResource` | `access_policy` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `database_name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `engine` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `host` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `owner` | `ForeignKey` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `provider_service` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `description` | `TextField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `access_mode` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `database` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `env_prefix` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `exposure` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `hostname` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `process` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `published_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `target_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `tls` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `scope` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `value` | `TextField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `internal` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `endpoint` | `OneToOneField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `host_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServiceProcess` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `entrypoint` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `environment` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `healthcheck` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `process_type` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `replicas` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `resources` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceRevision` | `activated_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `artifact_file` | `FileField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `build_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `config_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `endpoint_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `environment_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `graph_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `network_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `process_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `revision_number` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `runtime_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_keys` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_refs` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_deploy` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `volume_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecret` | `current_version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `description` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `actor` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `message` | `TextField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `is_enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShare` | `admin_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `group` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `is_active` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `preset` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `shared_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `target_user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `Service` | `active_revision` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `build_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deploy_started` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deployed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `desired_state` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `lifecycle_generation` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `plan` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `read_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `runtime_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy` | `OneToOneField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_kind` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `task_id` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `cwd` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `detail` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `exit_code` | `IntegerField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `meta` | `JSONField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `output_preview` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `session` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `success` | `BooleanField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellSession` | `closed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `last_used_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `mode` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `platform` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `root_path` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `token_hash` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `workdir` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `Volume` | `default_bind` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `default_mode` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_attempted_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_error` | `TextField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `released_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service_attachments` | `JSONField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `size_mb` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `users` | `src/users/models.py` | `PermissionMixin` | `is_superuser` | `BooleanField` | [field reference](../apps/users/field-reference.md#permissionmixin) |
| `users` | `src/users/models.py` | `Profile` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `image` | `ImageField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `order` | `IntegerField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Receipt` | `amount` | `DecimalField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `status` | `CharField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Rule` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `groups` | `Django PermissionsMixin` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `last_login` | `Django AbstractBaseUser` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `user_permissions` | `Django PermissionsMixin` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `user` | `OneToOneField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `User` | `balance` | `DecimalField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `birthdate` | `DateField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `color` | `PositiveSmallIntegerField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `date_joined` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `deletion_requested_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email` | `EmailField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `first_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_active` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_staff` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `last_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `national_id` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `password` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `phone_number_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `theme` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `username` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `uuid` | `CharField` | [field reference](../apps/users/field-reference.md#user) |

## Inheritance

Project-wide inherited fields are documented separately in [inherited-model-fields.md](inherited-model-fields.md). The field inventory intentionally records fields declared by each concrete/project model source; inherited framework fields are not duplicated once per model.

## Validation

Run:

```bash
python scripts/validate_documentation_contracts.py
```

Use `--check` in CI. Source code is authoritative; this inventory is intentionally strict and should be regenerated whenever routes or model declarations change.
