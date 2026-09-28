# Wagtail Admin Architecture and Coverage Audit

**Repository:** `nima-salamat/django-paas-deployer`  
**Branch:** `master`  
**Audit baseline:** current master at `f78c5be5eaa6`  
**Authority:** source code/current hooks; existing docs are secondary.

## Current Wagtail Coverage

The repository has moved away from the former implicit universal Wagtail registry. Current exposure is explicit per application.

| App | Current active Wagtail model/page surfaces | Current source |
|---|---|---|
| users | User (built-in Wagtail Users), Profile, Receipt (read-only), Rule (read-only after this change) | `src/config/apps.py`, `src/users/wagtail_admin/models.py` |
| auth_users | LoginSettings, InviteLink, InviteUsage (read-only), LoginLog (read-only) | `src/auth_users/wagtail_admin/models.py` |
| services | PrivateNetwork, Service, Volume; service inspection custom view | `src/services/wagtail_admin/models.py`, `src/services/wagtail_hooks.py` |
| plans | Plan | `src/plans/wagtail_admin/models.py` |
| deploy | Deploy (read-only after this change), DeployLog (read-only), BaseRuntimeImage, BaseRuntimeImageLease (read-only), SwarmCluster, SwarmNode | `src/deploy/wagtail_admin/models.py` |
| app_catalog | ApplicationInstance (read-only), ApplicationInstanceService (read-only) | `src/app_catalog/wagtail_admin/models.py` |
| logs | none | no `wagtail_hooks.py` |
| messenger | no model snippets; cache dashboard only | `src/messenger/wagtail_hooks.py` |
| tickets | none after this change | `src/tickets/wagtail_hooks.py` |
| custom_emails | EmailTemplate, EmailLog (read-only) | `src/custom_emails/wagtail_admin/models.py` |
| core | CoreSettings native Wagtail setting; Cache/system metrics custom views | `src/core/models.py`, `src/core/wagtail_hooks.py` |
| cms | HomePage Wagtail Page | `src/cms/models.py` |
| docs | none | no `wagtail_hooks.py` |
| deployments | no Django ORM models; runtime engine only | `src/deployments/` |

## Source-Derived Model Inventory and Decision Matrix

There are **77 concrete Django models** across the first-party model modules inspected. Each is assigned exactly one decision:

**A** Must be available in Wagtail  
**B** Useful to expose in Wagtail  
**C** Read-only operational visibility is useful  
**D** Better handled elsewhere  
**E** Must NOT be exposed because of security/correctness concerns  
**F** Internal/ephemeral model with no meaningful admin value

| App | Model | Wagtail exposure | Decision | Recommended shape | Ownership boundary |
|---|---|---|---|---|---|
| users | User | built-in Wagtail Users | A | canonical identity editor | `cms.viewsets.UserViewSet` |
| users | Receipt | current read-only snippet | C | list/detail only | payment mutation remains Django Admin |
| users | Profile | current snippet | B | editable supporting record | profile model/save constraints |
| users | Rule | current snippet, now read-only | C | inspect only | grants staff capability rules |
| auth_users | LoginSettings | current snippet | A | editable singleton, no add/delete | authentication policy |
| auth_users | Device | none | D | Django Admin/security workflow | existing device revoke |
| auth_users | UserSession | none | D | Django Admin/security workflow | existing session revoke |
| auth_users | UserContactChange | none | D | Django Admin/audit workflow | verification history |
| auth_users | InviteLink | current snippet | A | metadata edit; no token display | invite lifecycle |
| auth_users | InviteUsage | current read-only snippet | C | audit/detail | generated usage record |
| auth_users | AuthCode | none | E | no Wagtail surface | OTP credential |
| auth_users | LoginLog | current read-only snippet | C | audit/detail | authentication audit |
| services | PrivateNetwork | current snippet | B | desired metadata CRUD | service/network domain |
| services | Service | current snippet + inspection | A | high-level config + read-only inspection | Service/domain API |
| services | ServiceProcess | inspection only | C | contextual read-only | mutable desired process; revision is executable |
| services | ServiceRevision | inspection only | C | history/detail | immutable executable snapshot |
| services | ServiceEnvironmentVariable | inspection metadata only | C | key/scope/enabled; never raw secret value | service configuration API |
| services | ServiceSecret | inspection metadata only | C | key/version/description/enabled | secret store |
| services | ServiceSecretVersion | none | E | no Wagtail surface | immutable encrypted ciphertext |
| services | ServiceEndpoint | inspection only | C | contextual desired endpoint | service configuration API |
| services | ServicePortReservation | inspection only | C | contextual reservation | generated reservation state |
| services | ServiceNetworkAttachment | inspection only | C | contextual relation | service network API |
| services | DatabaseResource | inspection summary | C | metadata only | managed DB domain |
| services | DatabaseCredential | none | E | no Wagtail surface | encrypted credential material |
| services | ServiceDatabaseBinding | inspection only | C | contextual binding | DB configuration API |
| services | Volume | current snippet | B | allocation/mount editing with model invariants | Volume model/quota semantics |
| services | ServiceShare | inspection only | C | target/rules/expiry metadata | sharing API |
| services | ServiceShareMember | inspection only | C | member/rule metadata | sharing API |
| services | ServiceShareEvent | inspection only | C | audit history | generated share audit |
| services | ShellSession | none | D | existing Django Admin/security workflow | shell capability service |
| services | ShellAuditEvent | inspection, redacted | C | action/path/outcome only | forensic audit |
| plans | Plan | current snippet | A | policy CRUD | plan policy |
| deploy | Deploy | current read-only snippet | A | inspect + domain cancel action | deployment control plane |
| deploy | DeployLog | current read-only snippet | C | filtered diagnostic | separate deployment-log DB |
| deploy | BaseRuntimeImageLease | new read-only snippet | C | retention/protection inspection | base-image/deployment lifecycle |
| deploy | BaseRuntimeImage | current snippet | A | enable/auto-build + guarded build/renew | base image service |
| deploy | SwarmCluster | current guarded snippet | A | supported desired flag only | operator desired state + sync |
| deploy | SwarmNode | current guarded snippet | A | desired availability/labels only | Docker discovery owns identity/observations |
| logs | ServiceLogStream | none | C | future stream-health diagnostic | logs subsystem |
| logs | ServiceLogEntry | none | C | future bounded search only | high-volume event store |
| logs | ServiceLogUsage | none | C | future usage summary | log quota/accounting |
| logs | LogUsageDaily | none | C | future aggregate dashboard | daily aggregate |
| logs | CollectorHeartbeat | none | C | future collector-health view | collector service |
| app_catalog | ApplicationInstance | new read-only snippet | A | inspect + cancel installation | application coordinator |
| app_catalog | ApplicationInstanceService | new read-only snippet | C | child binding/dispatch inspection | application coordinator |
| messenger | UserBio | none | D | existing app admin/API | private user communications domain |
| messenger | Contact | none | D | existing app admin/API | private relationship data |
| messenger | Block | none | D | existing app admin/API | user privacy/moderation |
| messenger | ProfilePhotoPrivacy | none | D | existing app admin/API | privacy policy |
| messenger | ProfilePhotoAllowed | none | D | existing app admin/API | privacy relationship |
| messenger | Conversation | none | E | no Wagtail surface | participant-scoped private content |
| messenger | ConversationParticipant | none | E | no Wagtail surface | participant-scoped private data |
| messenger | GroupInviteLink | none | E | no Wagtail surface | invite/capability data |
| messenger | JoinRequest | none | D | existing group workflow | membership lifecycle |
| messenger | Message | none | E | no Wagtail surface | private communications content |
| messenger | MessengerEvent | none | E | no Wagtail surface | private event stream |
| messenger | MessageReaction | none | E | no Wagtail surface | private communication metadata |
| messenger | MessageReadReceipt | none | E | no Wagtail surface | participant-specific state |
| messenger | MessageAttachment | none | E | no Wagtail surface | private user file content |
| messenger | AttachmentViewOnceOpen | none | E | no Wagtail surface | security/privacy event |
| messenger | PinnedMessage | none | E | no Wagtail surface | conversation-private state |
| messenger | CallSession | none | E | no Wagtail surface | participant-scoped call metadata |
| messenger | CallSessionParticipant | none | E | no Wagtail surface | participant-scoped private data |
| tickets | Department | none after change | D | Django Admin/API | department authorization scope |
| tickets | DepartmentMembership | none after change | D | Django Admin/API | defines staff scope |
| tickets | Ticket | none after change | D | Django Admin/API | `CanManageTicket` + department scope |
| tickets | TicketMessage | none after change | D | Django Admin/API | support content workflow |
| tickets | TicketReadState | none after change | D | Django Admin/API | per-user derived state |
| tickets | TicketAttachment | none after change | D | Django Admin/API | customer file content |
| custom_emails | EmailTemplate | current snippet | A | editable template | template configuration |
| custom_emails | EmailLog | current read-only snippet | C | delivery audit | task/service owns side effect |
| docs | DocumentCategory | none | D | Django Admin/API | custom tree/reorder workflow |
| docs | Document | none | D | Django Admin/API | Markdown source + publish/reorder |
| docs | DocumentAsset | none | D | Django Admin/API | upload validation + asset endpoint |
| core | SystemSetting | none | D | Django Admin/API | masked, dynamic setting semantics |
| core | CoreSettings | native Wagtail setting | A | Wagtail settings | Wagtail settings framework |
| cms | HomePage | Wagtail Page | A | Page editor | CMS page tree |

## Source-of-truth decisions

### Service

`Service.desired_state`, selected/active deployment references, status and lifecycle timestamps are durable service/deployment state. Wagtail may edit supported high-level service configuration, but runtime state is read-only. The new service inspection page does not mutate any child model.

`ServiceProcess` is mutable desired process definition; `ServiceRevision` is an immutable executable snapshot. They therefore appear as inspection context, not competing Wagtail editors.

### Secrets

`ServiceSecret` is metadata. `ServiceSecretVersion.ciphertext` is encrypted immutable payload. `DatabaseCredential.password_ciphertext` is encrypted credential material. None of those payloads are a Wagtail write/read surface.

The service inspection view does not call `get_current_value()`, `resolve_value()` or expose ciphertext. `AuthCode` is excluded. `InviteLink.token` is not included in Wagtail panels.

### Deployment

`Deploy` is execution/provenance, not a configuration object. Wagtail is now read-only and supplies **Cancel deployment** only. Cancellation calls the existing `CancelDeploymentUseCase(DjangoDeploymentCancellationGateway())`.

`DeployLog` remains read-only and explicitly uses `DEPLOYMENT_LOG_DB_ALIAS`.

### Base runtime images / Swarm

`BaseRuntimeImage` is operator-owned registry configuration. Build and renew already use `request_base_runtime_image_build`; Wagtail never calls Docker directly.

`BaseRuntimeImageLease` is generated protection state and is read-only.

`SwarmCluster` and `SwarmNode` combine operator desired state with observed Docker state. Wagtail can edit the supported desired fields; node cluster identity, Docker ID and observations are read-only.

### Application catalog

`ApplicationInstance` is the coordinator's durable installed-application state. The Wagtail surface is read-only. Cancellation delegates to the existing `cancel_application_installation` task and its established synchronous `ApplicationStackExecutor` fallback.

`ApplicationInstanceService` is coordinator provenance linking child Services and Deploys; it is read-only. Catalog definition data and installation snapshots are not editable through Wagtail.

## Missing functionality and existing problems

### Critical correctness/security

**1. Writable deployment records.**  
Existing Wagtail panels allowed direct editing of deployment identity and archive fields. That conflicts with deployment-engine ownership. Fixed by read-only policy plus domain cancellation.

**2. Ticket Wagtail CRUD bypass.**  
Existing Wagtail ticket snippets allowed direct model mutation while `src/tickets/api/staff_tickets.py` uses department membership and `CanManageTicket`. Generic Wagtail forms did not reproduce those checks. Fixed by removing Wagtail registration.

**3. Privilege grants via User Rule.**  
`user.rule.rules` is consulted by application authorization code, including `docs.manage`. Wagtail now permits inspection but no mutation.

**4. LoginSettings singleton mismatch.**  
Django Admin already prevented add/delete. Wagtail now enforces the same invariant with a dedicated policy.

**5. SwarmNode re-parenting.**  
Wagtail previously exposed `cluster` as editable. The source has no supported Wagtail control-plane operation for re-parenting discovered Docker nodes. Cluster is now read-only.

### High operational value

**Installed application operator surface.** Durable installation state had no Wagtail home. It is now visible with status/stage/error/config metadata and a safe cancellation operation.

**Service operational inspection.** Operators previously had to reconstruct a service across multiple endpoints/models. The new read-only inspector consolidates process, endpoint, network, database, volume, share, revision, deployment and redacted audit/security metadata.

**Base-image retention visibility.** Lease records previously had no operator-facing surface even though active leases explain why an image cannot be reclaimed. They are now visible read-only.

### Medium usability/maintenance

**Logs.** `ServiceLogEntry` is potentially high-volume and belongs to a separate operational architecture. A future Wagtail diagnostic search/dashboard should use the existing query/retention services rather than generic CRUD.

**Operations dashboard.** A future staff read-only dashboard can combine existing durable data: deployment health, base-image build/lease state, Swarm sync health, collector heartbeat and logical storage anomalies. Runtime-only concepts should remain live queries, not fake ORM models.

## Permissions

| Surface/action | Access requirement |
|---|---|
| Service inspection | staff + `services.view_service` (superuser allowed) |
| Application records | Wagtail model view permission; cancel requires staff + `app_catalog.change_applicationinstance` |
| Deployment records | Wagtail model view permission; cancel requires staff + `deploy.change_deploy` |
| Base-image build/renew | staff + `deploy.change_baseruntimeimage` |
| Rule | existing view permission; no Wagtail add/change/delete |
| LoginSettings | existing model view/change permission; add/delete always denied |
| Swarm desired state | existing Wagtail model permissions; only supported desired fields editable |
| Secrets/credentials | no plaintext/ciphertext surface |

All new custom actions check staff status and the explicit change permission. They use existing domain/task methods for side effects.

## Admin versus Wagtail responsibility

**Wagtail canonical/complementary:** User identity, Plan policy, high-level Service configuration, EmailTemplate, operator deployment inspection/actions, base-image operator controls, Swarm desired state, installed application inspection/actions.

**Django Admin remains canonical for specialized workflows:** Device/session revocation, OTP/auth-code support, receipt payment mutation, ticket support and assignment, Docs tree/reorder/publish, SystemSetting, shell-security operations.

This avoids creating two independent state machines.

## Cross-app operator workflows

### Service → revision → deployment

The service inspection surface is the contextual owner. It shows active revision, selected deployment, bounded deployment history and configuration child state. It does not duplicate child editors.

### ApplicationInstance → child services → child deployments

The coordinator listing identifies child bindings. Cancellation remains coordinator-owned. Child Service/Deploy execution remains in their own domains.

### BaseRuntimeImage → lease → deployment

The lease listing gives an operator a durable reason for retention without direct Docker controls.

### User → security/support

User identity remains in Wagtail's built-in user editor. Authentication session/device security stays in existing admin/security workflows. Ticket support stays outside Wagtail because its staff authorization is department-based.

## Explicit exclusions

- `AuthCode`, `ServiceSecretVersion`, `DatabaseCredential`: credential-bearing records.
- Messenger private communication/content models: participant/user-scoped data with no equivalent Wagtail object-permission boundary.
- Ticket models: existing staff API/domain permission boundary is department-scoped.
- Docs models: existing Markdown/tree/publish/upload workflows are already implemented in Django Admin/API.
- `SystemSetting`: existing masked/dynamic settings semantics belong to Django Admin/API.
- `ShellSession`: short-lived security capability; existing shell services own termination/audit.
- `deployments/`: no ORM models exist; runtime execution is represented by existing durable Deploy/application data plus runtime services.

## Dashboard candidates

| Dashboard | Question answered | Data source | Refresh model | Safe actions |
|---|---|---|---|---|
| Deployment health | what is pending/running/failed/stale? | Deploy + deployment state/recovery | live/durable mix | cancel through use case |
| Base-image health | which images build/fail/are retained? | BaseRuntimeImage + Lease | durable | existing build/renew helper |
| Swarm health | is cluster/node state current/reachable? | SwarmCluster + SwarmNode | live sync timestamps | no destructive node control |
| Log collector health | are streams being collected? | CollectorHeartbeat + ServiceLogStream | periodic | diagnostic only |
| Storage anomalies | which services exceed logical allocation? | Service storage summary + Volume + Plan | durable logical | inspection only |

## Tests added/updated

The existing `core/tests/test_wagtail_cache_admin.py` contract tests were updated to remove the deleted universal registry assumptions and now verify:

- runtime/provenance/sensitive capability records are read-only;
- LoginSettings cannot be added/deleted;
- ticket Wagtail registration is disabled;
- service inspection source does not access secret payloads;
- deployment/application custom actions reject users without the required change permission;
- existing cache/Wagtail template and cache policy contracts remain intact.

## Implementation files

```text
src/app_catalog/wagtail_admin/__init__.py
src/app_catalog/wagtail_admin/models.py
src/app_catalog/wagtail_admin/views.py
src/app_catalog/wagtail_hooks.py
src/app_catalog/templates/app_catalog/wagtail/application_instance_cancel.html
src/deploy/wagtail_admin/models.py
src/deploy/wagtail_admin/views.py
src/deploy/wagtail_hooks.py
src/deploy/templates/deploy/wagtail/deployment_cancel.html
src/services/wagtail_admin/views.py
src/services/wagtail_hooks.py
src/services/templates/services/wagtail/service_inspect.html
src/users/wagtail_admin/models.py
src/auth_users/wagtail_admin/models.py
src/tickets/wagtail_hooks.py
src/core/tests/test_wagtail_cache_admin.py
src/cms/wagtail_hooks.py
documentation/reference/wagtail-admin-audit.md
```

## Verification checklist

- [x] Every concrete model has a Wagtail exposure decision.
- [x] Every active Wagtail surface has an owning source module.
- [x] Deployment execution state is read-only in Wagtail.
- [x] Secrets and credentials are not exposed.
- [x] New cancellation actions use established domain/task ownership.
- [x] Ticket department authorization is not bypassed by Wagtail.
- [x] Swarm node identity is not directly re-parentable.
- [x] DeployLog continues to use the separate database.
- [x] No fake Django models are introduced for runtime-only state.
