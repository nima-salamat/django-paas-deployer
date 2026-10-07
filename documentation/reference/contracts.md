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
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `deploy` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatch_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `dispatched_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `instance` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `sequence` | `PositiveIntegerField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service_key` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstanceService` | `service` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstanceservice) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `cancel_requested` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_snapshot` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `definition_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `deployed_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_code` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `error_message` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_deadline` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `execution_task_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `id` | `UUIDField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `name` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `network` | `OneToOneField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `secret_config` | `JSONField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `slug` | `SlugField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `software_version` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `stage` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `started_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `status` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `user` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `ApplicationInstance` | `variant_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#applicationinstance) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `catalog_id` | `CharField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `created_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `enabled` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `featured_override` | `BooleanField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `notes` | `TextField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_at` | `DateTimeField` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `app_catalog` | `src/app_catalog/models.py` | `CatalogPublication` | `updated_by` | `ForeignKey` | [field reference](../apps/app_catalog/field-reference.md#catalogpublication) |
| `core` | `src/core/models.py` | `CoreSettings` | `auto_public_url_handling` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_image_build_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_build` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_auto_register_existing` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `base_images_retain_after_deploy` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_batch_size` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_cleanup_target_percent` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_global_limit_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_keep_successful_deployments` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_service_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_cache_user_quota_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_cpu` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_max_ram_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_parallelism` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_pids_limit` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_resource_mode` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_shm_mb` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_slot_lease_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `build_wait_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `default_public_url_prefix` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `deploy_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_apt` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_composer` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_docker` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_go` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_npm` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `mirror_python` | `CharField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_batch_size` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_interval_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_max_recovery_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_recovery_enabled` | `BooleanField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_scheduler_lock_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_base_build_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `monitor_stale_worker_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `queued_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `shell_idle_timeout_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `stop_timeout_minutes` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `unexpected_death_grace_seconds` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_release_retention_days` | `PositiveIntegerField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `CoreSettings` | `volume_usage_warning_percent` | `FloatField` | [field reference](../apps/core/field-reference.md#coresettings) |
| `core` | `src/core/models.py` | `SystemSetting` | `category` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `created_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `description` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_editable` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `is_secret` | `BooleanField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `key` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `label` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `updated_at` | `DateTimeField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value_type` | `CharField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `core` | `src/core/models.py` | `SystemSetting` | `value` | `TextField` | [field reference](../apps/core/field-reference.md#systemsetting) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `body_preview` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `celery_task_id` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `error_message` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `failed_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `is_test` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient_email` | `EmailField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `recipient` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `sent_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `status` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `template` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `body` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `created_by` | `ForeignKey` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `description` | `TextField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `is_active` | `BooleanField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `name` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `subject` | `CharField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `updated_at` | `DateTimeField` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `acquired_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `base_image` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `deployment_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `released_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `architecture` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `auto_build` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_completed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_count` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_owner_deployment_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `build_task_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `definition_fingerprint` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `docker_host` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `enabled` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_repository` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `image_tag` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `last_error_details` | `JSONField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `logical_runtime` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `rebuild_requested_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `rebuild_requested` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `runtime_version` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `source_image` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `status` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `variant` | `CharField` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `deployment` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `last_used_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `pinned` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `reclaim_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `reclaimed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `size_bytes` | `BigIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `user` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `keep_successful_deployments` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `quota_mb` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `retention_days` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `service` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `user` | `OneToOneField` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `deploy` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `details` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `event_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `event_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `exception_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `level` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `progress` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `traceback` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `application_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `base_image_ready_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `base_image_wait_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cancel_requested` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cleanup_failures` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `cleanup_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `completed_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `config` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `container_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `created_by` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `error_message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `execution_task_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `health_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_digest` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_ref` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `image_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `network_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_previous_resource_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_resource_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation_started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `operation` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `previous_deploy` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `progress` | `PositiveSmallIntegerField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `reconciliation_required` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `recovery_metadata` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `release_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `revision` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `rollback_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_revision_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_spec_sha256` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `runtime_spec` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `service` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `source_revision` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `started_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `status_message` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `updated_file_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `version` | `DecimalField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `volume_status` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `worker_heartbeat_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `zip_file` | `FileField` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `attempts` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `deployment` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `dispatched_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `event_id` | `UUIDField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `event_type` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `level` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `next_attempt_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `occurred_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `payload` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `service_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `stage` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `deployment` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `kind` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `metadata` | `JSONField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `owned` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `retired_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `runtime_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `state` | `CharField` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `enabled` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `last_synced_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `manager_endpoint` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `name` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `address` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `cluster` | `ForeignKey` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `cpus` | `PositiveIntegerField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `desired_availability` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `desired_labels` | `JSONField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `docker_id` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `hostname` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `labels` | `JSONField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `last_error` | `TextField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `last_synced_at` | `DateTimeField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `manager_reachable` | `BooleanField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `memory_bytes` | `BigIntegerField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `observed_availability` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `observed_state` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `role` | `CharField` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `agent` | `src/agent/models.py` | `Agent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `name` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `description` | `TextField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `status` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `provisioning_source` | `CharField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `scopes` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `disabled_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `Agent` | `revoked_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agent) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `token_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `revoked_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `last_used_ip` | `GenericIPAddressField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentCredential` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentcredential) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_prefix` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `token_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `used_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentEnrollmentToken` | `issued_from_ip` | `GenericIPAddressField` | [field reference](../apps/agent/field-reference.md#agentenrollmenttoken) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `credential` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `action` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_type` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `request_id` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `occurred_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `success` | `BooleanField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `http_status` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `error_code` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `failure_domain` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `retryability` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `visibility` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `resource_effect` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `certainty` | `CharField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `duration_ms` | `PositiveIntegerField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentAuditEvent` | `metadata` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentauditevent) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `agent` | `ForeignKey` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `key` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `method` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `path` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `request_hash` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `state` | `CharField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `status_code` | `PositiveSmallIntegerField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `response_body` | `JSONField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `agent` | `src/agent/models.py` | `AgentIdempotencyRecord` | `expires_at` | `DateTimeField` | [field reference](../apps/agent/field-reference.md#agentidempotencyrecord) |
| `users` | `src/users/models.py` | `PermissionMixin` | `is_superuser` | `BooleanField` | [field reference](../apps/users/field-reference.md#permissionmixin) |
| `users` | `src/users/models.py` | `User` | `uuid` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `username` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `first_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `last_name` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `password` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email` | `EmailField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `email_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `phone_number_verified` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `theme` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `color` | `PositiveSmallIntegerField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `birthdate` | `DateField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `balance` | `DecimalField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_staff` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `deletion_requested_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `is_active` | `BooleanField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `date_joined` | `DateTimeField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `User` | `national_id` | `CharField` | [field reference](../apps/users/field-reference.md#user) |
| `users` | `src/users/models.py` | `Receipt` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `amount` | `DecimalField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Receipt` | `status` | `CharField` | [field reference](../apps/users/field-reference.md#receipt) |
| `users` | `src/users/models.py` | `Profile` | `order` | `IntegerField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `user` | `ForeignKey` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `image` | `ImageField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Profile` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#profile) |
| `users` | `src/users/models.py` | `Rule` | `user` | `OneToOneField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `updated_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `created_at` | `DateTimeField` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `last_login` | `Django AbstractBaseUser` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `groups` | `Django PermissionsMixin` | [field reference](../apps/users/field-reference.md#rule) |
| `users` | `src/users/models.py` | `Rule` | `user_permissions` | `Django PermissionsMixin` | [field reference](../apps/users/field-reference.md#rule) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_as_second_factor` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_auto_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `auto_activate_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_password_on_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `activate_after_successful_otp` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_invite_for_signup` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_username_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_password_recovery` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_email` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `password_recovery_via_phone` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `require_confirm_password` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `min_password_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `allow_login` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_message` | `TextField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `custom_login_closed_title` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_length` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_expire_minutes` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `otp_max_attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `max_active_sessions` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `session_eviction_policy` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `LoginSettings` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginsettings) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `name` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `platform` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `client` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `Device` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#device) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `session_id` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `device` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `credential_hash` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_seen_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `revoked_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `auth_generation` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `last_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserSession` | `metadata` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#usersession) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `public_id` | `UUIDField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `field` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `old_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `new_value` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `status` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `verified_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `cancelled_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `requested_ip` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `UserContactChange` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#usercontactchange) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `token` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `label` | `CharField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_by` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `max_uses` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `uses_count` | `PositiveIntegerField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `is_active` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `expires_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteLink` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#invitelink) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `invite` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `used_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `InviteUsage` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#inviteusage) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `contact` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `purpose` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `code` | `CharField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `attempts` | `PositiveSmallIntegerField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `AuthCode` | `updated_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#authcode) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user` | `ForeignKey` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `username` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `identifier` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `event` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `method` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `success` | `BooleanField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `ip_address` | `GenericIPAddressField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `user_agent` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `failure_reason` | `CharField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `extra` | `JSONField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `auth_users` | `src/auth_users/models.py` | `LoginLog` | `created_at` | `DateTimeField` | [field reference](../apps/auth_users/field-reference.md#loginlog) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `PrivateNetwork` | `description` | `TextField` | [field reference](../apps/services/field-reference.md#privatenetwork) |
| `services` | `src/services/models.py` | `Service` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `plan` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `read_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy` | `OneToOneField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `selected_deploy_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `active_revision` | `ForeignKey` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deploy_started` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `deployed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `task_id` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_kind` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `source_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `build_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `runtime_config` | `JSONField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `desired_state` | `CharField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `Service` | `lifecycle_generation` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#service) |
| `services` | `src/services/models.py` | `ServiceProcess` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `process_type` | `CharField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `entrypoint` | `TextField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `replicas` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `environment` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `healthcheck` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `resources` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceProcess` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceprocess) |
| `services` | `src/services/models.py` | `ServiceRevision` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `revision_number` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_deploy` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `artifact_file` | `FileField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `config_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `process_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_keys` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `secret_refs` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `source_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `build_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `runtime_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `environment_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `endpoint_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `volume_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `network_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `graph_snapshot` | `JSONField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceRevision` | `activated_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#servicerevision) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `value` | `TextField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `scope` | `CharField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceEnvironmentVariable` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceenvironmentvariable) |
| `services` | `src/services/models.py` | `ServiceSecret` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `key` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `current_version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `description` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecret` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesecret) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `secret` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `created_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceSecretVersion` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#servicesecretversion) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `process` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `target_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `published_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `exposure` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `hostname` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `tls` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServiceEndpoint` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceendpoint) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `endpoint` | `OneToOneField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `host_port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `protocol` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `state` | `CharField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServicePortReservation` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceportreservation) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `network` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `internal` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `ServiceNetworkAttachment` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicenetworkattachment) |
| `services` | `src/services/models.py` | `DatabaseResource` | `owner` | `ForeignKey` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `provider_service` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `engine` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `host` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `port` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `database_name` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `access_policy` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseResource` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#databaseresource) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `database` | `OneToOneField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `username` | `CharField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `password_ciphertext` | `TextField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `DatabaseCredential` | `version` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#databasecredential) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `database` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `alias` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `env_prefix` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `access_mode` | `CharField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `ServiceDatabaseBinding` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#servicedatabasebinding) |
| `services` | `src/services/models.py` | `Volume` | `name` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `service_attachments` | `JSONField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `default_bind` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `default_mode` | `CharField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `size_mb` | `PositiveIntegerField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `released_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_attempted_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `Volume` | `reclaim_error` | `TextField` | [field reference](../apps/services/field-reference.md#volume) |
| `services` | `src/services/models.py` | `ServiceShare` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `group` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `target_user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `shared_by` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `is_active` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `note` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `admin_only` | `BooleanField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShare` | `preset` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshare) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `rules` | `JSONField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareMember` | `is_enabled` | `BooleanField` | [field reference](../apps/services/field-reference.md#servicesharemember) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `share` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `actor` | `ForeignKey` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `message` | `TextField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ServiceShareEvent` | `metadata` | `JSONField` | [field reference](../apps/services/field-reference.md#serviceshareevent) |
| `services` | `src/services/models.py` | `ShellSession` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `token_hash` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `platform` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `root_path` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `workdir` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `mode` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `status` | `CharField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `last_used_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `expires_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellSession` | `closed_at` | `DateTimeField` | [field reference](../apps/services/field-reference.md#shellsession) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `service` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `user` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `session` | `ForeignKey` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `action` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `command` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `path` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `cwd` | `CharField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `exit_code` | `IntegerField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `success` | `BooleanField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `detail` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `meta` | `JSONField` | [field reference](../apps/services/field-reference.md#shellauditevent) |
| `services` | `src/services/models.py` | `ShellAuditEvent` | `output_preview` | `TextField` | [field reference](../apps/services/field-reference.md#shellauditevent) |

## Inheritance

Project-wide inherited fields are documented separately in [inherited-model-fields.md](inherited-model-fields.md). The field inventory intentionally records fields declared by each concrete/project model source; inherited framework fields are not duplicated once per model.

## Validation

Run:

```bash
python scripts/validate_documentation_contracts.py
```

Use `--check` in CI. Source code is authoritative; this inventory is intentionally strict and should be regenerated whenever routes or model declarations change.
