# Documentation completeness manifest

Audit baseline: `master`, 2026-11-04. Source code remains authoritative. This manifest lists persisted domain models separately from status enums and other non-model classes. Run `python scripts/agent_docs.py audit` for the current static source-to-doc check.

## Installed first-party apps

`agent`, `users`, `auth_users`, `services`, `plans`, `deploy`, `deployments`, `logs`, `app_catalog`, `messenger`, `tickets`, `custom_emails`, `docs`, `core`, `cms`.

## Persisted models

The following are model classes, not choices/enums. The canonical per-app `models.md` explains model purpose and authority; the paired `field-reference.md` records declared fields and field metadata.

- `agent`: Agent, AgentCredential, AgentEnrollmentToken, AgentAuditEvent, AgentIdempotencyRecord
- `app_catalog`: ApplicationInstance, ApplicationInstanceService, CatalogPublication
- `auth_users`: LoginSettings, Device, UserSession, UserContactChange, InviteLink, InviteUsage, AuthCode, LoginLog
- `cms`: HomePage (Wagtail Page model)
- `core`: SystemSetting, CoreSettings
- `custom_emails`: EmailTemplate, EmailLog
- `deploy`: BuildArtifact, Release, Deploy, DeploymentResource, DeploymentEventOutbox, DeployLog, BuildCacheArtifact, BuildCacheQuota, BaseRuntimeImageLease, BaseRuntimeImage, SwarmCluster, SwarmNode
- `docs`: DocumentCategory, Document, DocumentAsset
- `logs`: ServiceLogStream, ServiceLogEntry, ServiceLogUsage, LogUsageDaily, CollectorHeartbeat
- `messenger`: UserBio, Contact, Block, ProfilePhotoPrivacy, ProfilePhotoAllowed, Conversation, MatrixIdentity, MatrixDevice, ConversationParticipant, GroupInviteLink, JoinRequest, Message, MessengerEvent, MessageReaction, MessageReadReceipt, MessageAttachment, AttachmentViewOnceOpen, PinnedMessage, CallSession, CallSessionParticipant
- `plans`: Plan
- `services`: PrivateNetwork, Service, ServiceProcess, ServiceRevision, ServiceEnvironmentVariable, ServiceSecret, ServiceSecretVersion, ServiceEndpoint, ServicePortReservation, ServiceNetworkAttachment, DatabaseResource, DatabaseCredential, ServiceDatabaseBinding, Volume, ServiceShare, ServiceShareMember, ServiceShareEvent, ShellSession, ShellAuditEvent
- `tickets`: Department, DepartmentMembership, Ticket, TicketMessage, TicketReadState, TicketAttachment
- `users`: User, Receipt, Profile, Rule

`users.PermissionMixin` is an abstract model mixin and is documented in `users/models.md`; it is not a concrete domain table in the inventory above.

## Important non-model choices and policy types

Do not count these as database models: `app_catalog.ApplicationStatus`, `auth_users.SessionEvictionPolicy`, deploy status/cleanup/resource/release choice classes, model-nested status/type/protocol/role/scope/availability choices, and other `TextChoices` declarations. Their owning state/API contracts document valid values and transitions.

## Serializers

- `app_catalog`: ApplicationInstanceSerializer
- `auth_users`: SessionTokenRefreshSerializer
- `custom_emails`: EmailTemplateSerializer, EmailTemplatePreviewSerializer, EmailSendSerializer, EmailLogSerializer
- `deploy`: DeployLogSerializer, DeploySerializer
- `docs`: CategorySerializer, DocumentAssetSerializer, DocumentSerializer, DocumentCreateSerializer
- `messenger`: UserMiniSerializer, MessageAttachmentSerializer, ReactionSerializer, MessageSerializer, ParticipantSerializer, ConversationListSerializer, ConversationDetailSerializer, GroupInviteLinkSerializer, ContactSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer, JoinRequestSerializer
- `plans`: PlanSerializer, UnauthorizedPlanSerializer
- `services`: PrivateNetworkSerializer, ServiceSerializer, GetServiceSerializer, VolumeSerializer, ServiceShareSerializer, ServiceShareCreateSerializer, ServiceShareUpdateSerializer, ServiceShareEventSerializer
- `tickets`: DepartmentSerializer, UserBriefSerializer, ServiceBriefSerializer, DeployBriefSerializer, TicketAttachmentSerializer, TicketMessageSerializer, TicketListSerializer, TicketDetailSerializer, TicketCreateSerializer, TicketMessageCreateSerializer, TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer
- `users`: CreateUserSerializer, GetUserSerializer, SetPasswordSerializer, ChangePasswordSerializer, RemovePasswordSerializer, UpdateUserSerializer, AddImageProfileSerializer, OrderImageProfileSerializer, ProfileImagerSerializer, DeletePasswordSerializer

Serializer declarations that are plain API helpers or nested serializers should be documented beside the owning API serializer rather than misclassified as persistent models.

## Background/event inventory

| App | Tasks/background | Signals / consumers |
|---|---|---|
| app_catalog | start_application_installation, gate_application_service, advance_application_service, application_service_failed, cancel_application_installation, delete_application_installation, reconcile_application_installations | Application coordinator and child-service lifecycle |
| auth_users | session/authentication lifecycle, token refresh/revoke, contact verification and email helpers | Session/device/auth-code lifecycle |
| core | send_code_via_email, unzip_files, setting seed/cache operations | post_migrate setting seed, SystemSetting cache |
| custom_emails | send_email_log_task, send_bulk_email_task | Asynchronous delivery and retry |
| deploy | deployment event outbox dispatcher, build/base-image/cache helpers and persistence models | Deploy cleanup and event projection |
| deployments | deploy, stop, restart_service, build_base_runtime_image, reclaim_released_volumes, expire_idle_shell_sessions_task; Beat monitor_services/sync_swarm_infrastructure | Execution, reconciliation and runtime workers |
| logs | retain_all_services, reconcile_usage | Runtime ingestion, retention and usage accounting |
| messenger | finalize_unanswered_call, deliver_scheduled_messages, purge_view_once_if_complete | MessengerConsumer; message, media, conversation and call lifecycle |
| plans | plan policy/cache operations | Plan cache invalidation |
| services | revisioning, shell expiry, share cleanup | Service/Volume/PrivateNetwork cleanup/cache; ServiceConsumer |
| tickets | ticket notification/read-state work | Ticket activity/cache; TicketConsumer |
| users | account/session/resource deletion | User deletion, session/cache/resource cleanup and lifecycle fencing |

## Route source inventory

The root mount table is `src/config/urls.py`. App-level route declarations and router registrations are:

- `agent`: `src/agent/urls.py`, `src/agent/user_urls.py` — `/agent/v1/` and `/api/agents/`
- `app_catalog`: `src/app_catalog/urls.py` — `/api/application-catalog/`
- `auth_users`: `src/auth_users/urls.py` — `/auth/`
- `core`: `src/core/settings_urls.py`, `src/core/urls.py` — `/api/system/` and protected media
- `custom_emails`: `src/custom_emails/urls.py` — `/api/emails/`
- `deploy`: `src/deploy/urls.py` — `/deploy/`
- `docs`: `src/docs/urls.py` — `/api/docs/`
- `messenger`: `src/messenger/urls.py` — `/api/messenger/`
- `plans`: `src/plans/urls.py` — `/plans/`
- `services`: `src/services/urls.py`, `src/services/network_api_urls.py`, `src/services/volume_api_urls.py` — `/services/`, `/api/networks/`, `/api/volumes/`
- `tickets`: `src/tickets/urls.py` — `/api/tickets/`
- `users`: `src/users/urls.py`, `src/users/api_urls.py` — `/users/` and `/api/users/`

The `logs` app does not have its own public router; service-log read/export is exposed by Services and Agent APIs, and ingestion is an internal Services route. `cms` does not expose an app-owned REST router; Wagtail owns its page/admin surface. `deployments` is the internal execution subsystem, not a separate public HTTP API; client deployment endpoints live in `deploy`, `services`, `app_catalog` and the Agent facade.

## API documentation entry points

Each public app surface has an owning `api.md` or `api-reference.md` under `documentation/apps/<app>/`. Detailed guides list methods, route patterns, behavior, permission boundaries and important request/response rules. The Agent guide is `documentation/apps/agent/api.md`; Logs and CMS explicitly describe their embedded/non-router boundaries.

Start from [the cross-app API contract index](api-contracts.md), then follow the owning app reference. The detailed contract inventory in `contracts.md` is source-derived route/router/model/field evidence; it is not a substitute for endpoint behavior documentation.

## High-risk exact route assertions

- Messenger join decisions: `conversations/<int:pk>/join-requests/<int:req_id>/action/` POST.
- Messenger caller requests: `me/join-requests/` GET; cancellation: `join-requests/<int:req_id>/` DELETE.
- Messenger pinned messages: `conversations/<int:pk>/pinned-messages/` GET.
- Messenger invite revoke: `conversations/<int:pk>/invite-links/<int:link_id>/revoke/` POST.
- Messenger call join and active: both GET.
- Services user routers: service, networks, volume, with list/retrieve/create/update/partial_update/destroy routes.
- Services admin routers: admin/services, admin/networks, admin/volumes.
- Services network/volume aliases: `/api/networks/` and `/api/volumes/`.
- Ready App installation/delete: creation and cancellation/deletion are durable coordinator intents; DELETE may return while asynchronous cleanup converges.
- Agent endpoints: the exact scope, method, idempotency and throttle matrix is maintained in `documentation/apps/agent/api.md` and generated from `src/agent/contracts.py`.

## Agent documentation search

Run from the repository root (Python standard library only):

```bash
python scripts/agent_docs.py search ServiceRevision --kind model --json
python scripts/agent_docs.py search "/agent/v1/services/{service_id}/rebuild" --kind api --json
python scripts/agent_docs.py search "runtime reconciliation" --kind system
python scripts/agent_docs.py audit --json
```

The lookup indexes Markdown headings/body, Django model class declarations and statically declared URL/router entries. Results contain documentation/source paths and line numbers where available. See [Agent documentation search](agent-documentation-search.md) for output fields, limits and how to extend the index.

## Maintenance rule

When adding a model, serializer, route, Celery task, signal, consumer or Wagtail hook, update the owning app documentation in the same change and run both:

```bash
python scripts/validate_documentation_contracts.py
python scripts/agent_docs.py audit
```

The first validator checks source-derived API/router/action/model/field inventory parity. The Agent docs audit checks whether detected model classes are named in their app model guide and whether route-owning apps have an API guide. Both are static checks; dynamically composed behavior still requires human review.
