# Documentation completeness manifest

Audit baseline: master, 2026-09-28. Source code remains authoritative. This Markdown inventory makes omissions visible when implementation surfaces change.

## Installed first-party apps
agent, users, auth_users, services, plans, deploy, deployments, logs, app_catalog, messenger, tickets, custom_emails, docs, core, cms.

## Models
- agent: Agent, AgentCredential, AgentEnrollmentToken, AgentAuditEvent, AgentIdempotencyRecord
- app_catalog: ApplicationStatus, ApplicationInstance, ApplicationInstanceService
- auth_users: LoginSettings, SessionEvictionPolicy, Device, UserSession, UserContactChange, InviteLink, InviteUsage, AuthCode, LoginLog
- core: SystemSetting
- custom_emails: EmailTemplate, EmailLog
- deploy: Deploy, DeployLog, BaseRuntimeImageLease, BaseRuntimeImage, SwarmCluster, SwarmNode
- logs: ServiceLogStream, ServiceLogEntry, ServiceLogUsage, LogUsageDaily, CollectorHeartbeat
- messenger: UserBio, Contact, Block, ProfilePhotoPrivacy, ProfilePhotoAllowed, Conversation, ConversationParticipant, GroupInviteLink, JoinRequest, Message, MessengerEvent, MessageReaction, MessageReadReceipt, MessageAttachment, AttachmentViewOnceOpen, PinnedMessage, CallSession, CallSessionParticipant
- plans: Plan
- services: PrivateNetwork, Service, ServiceProcess, ServiceRevision, ServiceEnvironmentVariable, ServiceSecret, ServiceSecretVersion, ServiceEndpoint, ServicePortReservation, ServiceNetworkAttachment, DatabaseResource, DatabaseCredential, ServiceDatabaseBinding, Volume, ServiceShare, ServiceShareMember, ServiceShareEvent, ShellSession, ShellAuditEvent
- tickets: Department, DepartmentMembership, Ticket, TicketMessage, TicketReadState, TicketAttachment
- users: User, Receipt, Profile, Rule

## Serializers
- app_catalog: ApplicationInstanceSerializer
- auth_users: SessionTokenRefreshSerializer
- custom_emails: EmailTemplateSerializer, EmailTemplatePreviewSerializer, EmailSendSerializer, EmailLogSerializer
- deploy: DeployLogSerializer, DeploySerializer
- docs: CategorySerializer, DocumentAssetSerializer, DocumentSerializer, DocumentCreateSerializer
- messenger: UserMiniSerializer, MessageAttachmentSerializer, ReactionSerializer, MessageSerializer, ParticipantSerializer, ConversationListSerializer, ConversationDetailSerializer, GroupInviteLinkSerializer, ContactSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer, JoinRequestSerializer
- plans: PlanSerializer, UnauthorizedPlanSerializer
- services: PrivateNetworkSerializer, ServiceSerializer, GetServiceSerializer, VolumeSerializer, ServiceShareSerializer, ServiceShareCreateSerializer, ServiceShareUpdateSerializer, ServiceShareEventSerializer
- tickets: DepartmentSerializer, UserBriefSerializer, ServiceBriefSerializer, DeployBriefSerializer, TicketAttachmentSerializer, TicketMessageSerializer, TicketListSerializer, TicketDetailSerializer, TicketCreateSerializer, TicketMessageCreateSerializer, TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer
- users: CreateUserSerializer, GetUserSerializer, SetPasswordSerializer, ChangePasswordSerializer, RemovePasswordSerializer, UpdateUserSerializer, AddImageProfileSerializer, OrderImageProfileSerializer, ProfileImagerSerializer, DeletePasswordSerializer

## Background/event inventory
| App | Tasks/background | Signals | Consumers |
|---|---|---|---|
| app_catalog | start_application_installation, gate_application_service, advance_application_service, application_service_failed, cancel_application_installation, reconcile_application_installations | none; User deletion uses model RESTRICT semantics for compound application graphs | none |
| auth_users | auth/session protocol, email helpers | auth/session hooks | none |
| core | send_code_via_email, unzip_files | post_migrate setting seed, SystemSetting cache | none |
| custom_emails | send_email_log_task, send_bulk_email_task | none | none |
| deploy | execution helpers | Deploy cleanup | none |
| deployments | deploy, stop, restart_service, build_base_runtime_image, reclaim_released_volumes, expire_idle_shell_sessions_task; Beat monitor_services/sync_swarm_infrastructure | lifecycle/runtime hooks | deployments consumer |
| logs | retain_all_services, reconcile_usage | none | none |
| messenger | finalize_unanswered_call, deliver_scheduled_messages, purge_view_once_if_complete | attachment/conversation/message cleanup; User deletion leave/cache cleanup | MessengerConsumer |
| plans | none | plan cache invalidation | none |
| services | revisioning, shell expiry, share cleanup | Service/Volume/PrivateNetwork cleanup/cache | ServiceConsumer |
| tickets | none | Ticket activity/cache | TicketConsumer |
| users | none | user/session/cache/resource cleanup; lifecycle fencing/network attachment preparation | none |

## Route source inventory
agent: src/agent/urls.py, src/agent/user_urls.py
app_catalog: src/app_catalog/urls.py  
auth_users: src/auth_users/urls.py  
core: src/core/urls.py, src/core/settings_urls.py  
custom_emails: src/custom_emails/urls.py  
deploy: src/deploy/urls.py  
messenger: src/messenger/urls.py  
plans: src/plans/urls.py  
services: src/services/urls.py, src/services/network_api_urls.py, src/services/volume_api_urls.py  
tickets: src/tickets/urls.py  
users: src/users/urls.py, src/users/api_urls.py  
docs: src/docs/urls.py

## High-risk exact route assertions
- Messenger join decisions: conversations/<int:pk>/join-requests/<int:req_id>/action/ POST.
- Messenger caller requests: me/join-requests/ GET; cancellation: join-requests/<int:req_id>/ DELETE.
- Messenger pinned messages: conversations/<int:pk>/pinned-messages/ GET.
- Messenger invite revoke: conversations/<int:pk>/invite-links/<int:link_id>/revoke/ POST.
- Messenger call join and active: both GET.
- Services user routers: service, networks, volume, with list/retrieve/create/update/partial_update/destroy routes.
- Services admin routers: admin/services, admin/networks, admin/volumes.
- Services network/volume aliases: /api/networks/ and /api/volumes/.

## Maintenance rule
When adding a model, serializer, route, Celery task, signal, consumer or Wagtail hook, update this manifest and the owning app reference in the same change.