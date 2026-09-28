# services API

Root mount: /services/. Additional volume/network roots are included from services.

All user-facing endpoints authenticate with SessionJWTAuthentication + IsAuthenticated. User APIs are owner-scoped unless explicitly using share-aware access. Admin ViewSets allow cross-user access only with the configured services.view/services.manage rules.

## Lifecycle and runtime-control routes

| Method | Route | Actual effect |
|---|---|---|
| POST | /start_service/ | Resolves the target Service using owner/share permission, locks the Service, records lifecycle intent and queues deployments.celery.tasks.deploy. force_rebuild may request a rebuild when the caller has can_rebuild. |
| POST | /stop_service/ | Resolves ownership/share, locks the lifecycle operation, requests stop/cancel and queues/executes the appropriate operations path. |
| POST | /restart_service/ | Queues an ordered restart without creating a new ServiceRevision. It operates on the current runtime release. |
| POST | /force_cancel_deploy/ | Cancels a specific deployment, using deploy_id when supplied or service_id as legacy input. |
| POST | /purge_service_runtime/ | Force-removes runtime artifacts for the authorized Service; this is destructive runtime cleanup, not desired-state deletion. |
| POST | /service_status/ | Returns current Service/runtime status information. |
| POST | /admin/start_service/ | Same start control for staff with services.manage; cross-user target allowed. |
| POST | /admin/stop_service/ | Staff runtime stop for any authorized Service. |
| POST | /admin/purge_service_runtime/ | Staff force runtime purge. |

These routes are control-plane entry points. They do not make services a Docker runtime implementation; they enqueue/use deployments.

## Declarative configuration

| Method | Route | Effect |
|---|---|---|
| GET, PATCH | /service/<service_id>/configuration/ | Reads/updates desired executable Service configuration. Changes become effective through a later revision/deployment. |
| GET, PATCH | /service/<service_id>/environment/ | Lists/updates environment-variable intent. Secret-backed entries are represented through secret references. |
| GET, POST, PATCH, DELETE | /service/<service_id>/secrets/ | Manages ServiceSecret identities/versions without returning plaintext secret values through ordinary reads. |
| GET, POST, PATCH, DELETE | /service/<service_id>/endpoints/ | Manages desired network exposure. Endpoint changes are revision/build/runtime inputs, not direct Docker mutations. |
| GET, POST, PATCH, DELETE | /service/<service_id>/networks/ | Manages explicit ServiceNetworkAttachment rows. |
| GET, POST, PATCH, DELETE | /service/<service_id>/databases/ | Reads/updates ServiceDatabaseBinding relationships. |
| GET, POST | /service/<service_id>/database-resources/ | Lists/creates database-resource bindings from owner-visible provider Services. |
| GET, POST | /service/<service_id>/revisions/ | Lists existing immutable revisions and creates a new snapshot from current Service state. |
| GET | /service/<service_id>/revisions/<revision_id>/ | Retrieves an owned revision. |
| POST | /service/<service_id>/revisions/<revision_id>/rollback/ | Requests deployment of the selected historical revision; it does not mutate that revision. |

Each configuration endpoint calls a common service resolver plus action-specific share permission. Mutable configuration is rejected while the Service is in protected transitional states.

## Service/volume/network ViewSets

The user ServiceViewSet provides list/create/update/retrieve/delete over the durable Service resource. Its list is “mine” only; shared Services are exposed through dedicated share-aware endpoints. Non-owner shared access can retrieve/update when its effective rules permit but cannot destroy the Service.

PrivateNetworkViewSet is current-user scoped.

VolumeViewSet enforces exclusive Service ownership and plan storage quota. Soft detach keeps service ownership/quota; hard release to service=None frees quota. Creating an attached volume calls attach_to_service.

## Sharing

| Route | Purpose |
|---|---|
| /services/mine/ | Owned Services only. |
| /services/shared/ | Shares received/created according to scope=received|created|all. Group visibility depends on active Messenger ConversationParticipant membership. |
| /services/unified/ | UI-oriented owned+received split. |
| /services/share/ | Create ServiceShare for exactly one target user or Messenger group. |
| /services/shares/<id>/ | GET by recipient/owner; owner-only update/deactivate. |
| /services/shares/<id>/permissions/ | Effective permissions for current viewer. |
| /services/shares/<id>/events/ | Share audit events for authorized owner/recipient. |
| /services/shares/<id>/leave/ | Direct recipient leaves a share. |
| /services/shares/<id>/members/ | GET/PUT group share member overrides. |
| /services/share-presets/ | Preset/effective rule helpers. |
| /services/groups/<group_id>/shares/ | Active Service shares targeting a Messenger group; caller must be active group participant. |
| /services/<service_id>/access/ | Ownership plus effective permissions for the caller. |

Share JSON rules are normalized and unknown presets are rejected. Group service access is tied to live Messenger membership; leaving/removal can trigger ServiceShare cleanup.

## Shell

The shell routes all begin with _resolve(..., action="can_shell"), authenticate a per-session shell token, then resolve the runtime service. File operations are restricted to the session workspace. Audit endpoints expose activity but never make the audit log itself a permission grant.

## Volume file/runtime routes

/volume/<id>/files/ lists files through a Docker volume/helper-container path when host mount access is unavailable.

/volume/<id>/download/ archives the volume and streams a bounded download.

/admin/logging/health/ exposes runtime log collector health to the appropriate admin surface.

## Authorization chain

~~~text
request
 -> SessionJWTAuthentication
 -> service resolver
      owner OR effective ServiceShare permission
 -> endpoint-specific action check
 -> serializer/model or lifecycle transaction
 -> transaction.on_commit task/event where external work is needed
~~~

A UI-hidden control is never considered authorization.

## Relevant implementation files

src/services/urls.py; src/services/api/common.py; user_services.py; configuration.py; runtime.py; sharing.py; shell.py; volume_files.py; admin_services.py.
