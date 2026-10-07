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

## Inheritance

Project-wide inherited fields are documented separately in [inherited-model-fields.md](inherited-model-fields.md). The field inventory intentionally records fields declared by each concrete/project model source; inherited framework fields are not duplicated once per model.

## Validation

Run:

```bash
python scripts/validate_documentation_contracts.py
```

Use `--check` in CI. Source code is authoritative; this inventory is intentionally strict and should be regenerated whenever routes or model declarations change.
