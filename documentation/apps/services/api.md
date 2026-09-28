# services API

Canonical mount: /services/. Additional aliases are mounted at /api/volumes/ and /api/networks/.

All user-facing APIs use SessionJWTAuthentication + IsAuthenticated. User ViewSets scope querysets to the authenticated user even for staff. Share-aware actions resolve ServiceShare rules. Admin ViewSets enforce services.view/services.manage or the documented resource-specific permission.

## Router-generated user APIs

| ViewSet | Exact route | Methods | Contract |
|---|---|---|---|
| ServiceViewSet | /services/service/ | GET list, POST create | Current-user Services; creation changes durable desired state, not Docker directly. |
| ServiceViewSet | /services/service/<uuid:pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Owner-scoped; mutation changes desired state and deletion invokes cleanup. |
| PrivateNetworkViewSet | /services/networks/ | GET list, POST create | Current-user networks. |
| PrivateNetworkViewSet | /services/networks/<pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Desired network state; deletion has runtime cleanup. |
| VolumeViewSet | /services/volume/ | GET list, POST create | Current-user volumes; creation enforces ownership/quota. |
| VolumeViewSet | /services/volume/<pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Exclusive Service ownership and release/reclaim rules apply. |

The same PrivateNetworkViewSet and VolumeViewSet are mounted under /api/networks/ and /api/volumes/ with the same standard router actions.

## Router-generated admin APIs

| ViewSet | Exact route | Methods | Authorization |
|---|---|---|---|
| AdminServiceViewSet | /services/admin/services/ | GET list, POST create | Staff services.view/manage. |
| AdminServiceViewSet | /services/admin/services/<uuid:pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Cross-user service management. |
| AdminPrivateNetworkViewSet | /services/admin/networks/ | GET list, POST create | Staff networks.manage or services.manage. |
| AdminPrivateNetworkViewSet | /services/admin/networks/<pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Cross-user network management. |
| AdminVolumeViewSet | /services/admin/volumes/ | GET list, POST create | Staff volumes.manage or services.manage. |
| AdminVolumeViewSet | /services/admin/volumes/<pk>/ | GET retrieve, PUT update, PATCH partial_update, DELETE destroy | Cross-user volume management. |

## Runtime/lifecycle controls

| Method | Exact route | Meaning |
|---|---|---|
| POST | /services/start_service/ | Owner/share-authorized start; records lifecycle intent and dispatches deployment work. |
| POST | /services/stop_service/ | Owner/share-authorized stop/cancel path. |
| POST | /services/restart_service/ | Restart current runtime release; does not itself create a revision. |
| POST | /services/force_cancel_deploy/ | Cancel an authorized deployment execution. |
| POST | /services/purge_service_runtime/ | Destructive runtime cleanup, not desired-state deletion. |
| POST | /services/admin/start_service/ | Staff cross-user start. |
| POST | /services/admin/stop_service/ | Staff cross-user stop. |
| POST | /services/admin/purge_service_runtime/ | Staff cross-user runtime purge. |
| POST | /services/service_status/ | Current lifecycle/runtime status. |

## Configuration/revision APIs

| Method | Exact route | Contract |
|---|---|---|
| GET, PATCH | /services/service/<uuid:service_id>/configuration/ | Desired executable configuration. |
| GET, POST, DELETE | /services/service/<uuid:service_id>/environment/ | ServiceEnvironmentVariable intent; secret-backed values use secret references. |
| GET, POST, DELETE | /services/service/<uuid:service_id>/secrets/ | Secret identities/versions; plaintext is not ordinary read output. |
| GET, POST, DELETE | /services/service/<uuid:service_id>/endpoints/ | Desired exposure; model validation enforces protocol/port/path rules. |
| GET, POST, DELETE | /services/service/<uuid:service_id>/networks/ | ServiceNetworkAttachment rows. |
| GET, POST, DELETE | /services/service/<uuid:service_id>/databases/ | ServiceDatabaseBinding rows. |
| GET, POST | /services/service/<uuid:service_id>/database-resources/ | Visible database resources. |
| GET | /services/service/<uuid:service_id>/revisions/ | List immutable revisions. |
| GET | /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/ | Read one owned revision. |
| POST | /services/service/<uuid:service_id>/revisions/<uuid:revision_id>/rollback/ | Deploy an existing revision without editing it. |

## Shell/log/volume routes

The literal shell prefix is services/services because services/urls.py registers that path:

/services/services/<uuid:service_id>/shell/
/services/services/<uuid:service_id>/shell/catalog/
/services/services/<uuid:service_id>/shell/session/
/services/services/<uuid:service_id>/shell/session/replace/
/services/services/<uuid:service_id>/shell/command/
/services/services/<uuid:service_id>/shell/close/
/services/services/<uuid:service_id>/shell/file/
/services/services/<uuid:service_id>/shell/tree/
/services/services/<uuid:service_id>/shell/tree/meta/
/services/services/<uuid:service_id>/shell/audit/
/services/services/<uuid:service_id>/shell/audit/export/
/services/services/<uuid:service_id>/shell/history/
/services/services/<uuid:service_id>/shell/env/
/services/services/<uuid:service_id>/shell/health/

Runtime logs: /services/service/<uuid:pk>/logs/ and /services/service/<uuid:pk>/logs/export/. Admin collector health: /services/admin/logging/health/. Volume files: /services/volume/<uuid:pk>/files/ and /services/volume/<uuid:pk>/download/.

## Sharing

| Method | Exact route | Contract |
|---|---|---|
| GET | /services/services/mine/ | Owned services. |
| GET | /services/services/shared/ | Shares visible to caller. |
| GET | /services/services/unified/ | Owned + shared projection. |
| POST | /services/services/share/ | Create ServiceShare for exactly one user or Messenger group. |
| GET, PATCH, DELETE | /services/services/shares/<uuid:pk>/ | Read/update/deactivate share according to owner/recipient rules. |
| GET | /services/services/shares/<uuid:pk>/permissions/ | Effective viewer permissions. |
| GET | /services/services/shares/<uuid:pk>/events/ | Share audit history. |
| GET | /services/services/groups/<int:group_id>/shares/ | Active group-targeted shares. |
| POST | /services/services/shares/<uuid:pk>/leave/ | Recipient leaves a share. |
| GET, PUT | /services/services/shares/<uuid:pk>/members/ | Group-share member overrides. |
| GET | /services/services/share-presets/ | Supported presets. |
| GET | /services/services/<uuid:service_id>/access/ | Ownership/effective access. |

Validation boundary: request -> authentication -> owner/share authorization -> serializer/API validation -> model/domain constraints -> lifecycle/revision transaction -> on_commit -> deployments runtime work.

Source: src/services/urls.py, src/services/network_api_urls.py, src/services/volume_api_urls.py, src/services/api/*.py.