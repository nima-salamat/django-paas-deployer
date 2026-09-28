# services serializers

## ServiceSerializer

Used for Service create/update. Existing name is read-only. service_name/service_host/storage are derived. Plan changes are rejected for Services in queued/deploying/stopping; deeper domain validation still occurs in model/API code.

The serializer is sensitive to authenticated owner/share context, current Service lifecycle state and plan compatibility. Changing a field here without tracing its persistence into ServiceRevision can create the “accepted but ignored at runtime” bug.

## GetServiceSerializer

Read-oriented service payload with nested Plan/PrivateNetwork and derived owner/runtime naming/storage summary. It is not an authorization bypass; the API scopes the object first.

## PrivateNetworkSerializer

Creates/updates user-owned PrivateNetwork names/descriptions. Docker network identity remains derived by the model/runtime layer.

## VolumeSerializer

Validates positive size and Service ownership/quota. service_name/status/attached_services/count and lifecycle/reclaim fields are derived/read-only. attach/detach/release semantics are delegated to Volume methods because these operations need locking and quota invariants.

## ServiceShare serializers

ServiceShareCreateSerializer requires exactly one group_id or target_user_id and normalizes rules/preset. ServiceShareUpdateSerializer updates owner-controlled rule/active/expiry/note/admin fields. ServiceShareSerializer computes viewer-specific my_permissions and target metadata.

Share serializers are highly sensitive to the authenticated viewer and Messenger membership. Client-supplied rules are policy input, not arbitrary permission JSON; unknown/unsafe rules are rejected or normalized.

## Mapping and validation placement

~~~text
PATCH service configuration
 -> serializer field validation
 -> service API/domain checks
 -> Service.save/full_clean
 -> later ensure_revision_for_deploy
 -> DeploymentPlan/runtime
~~~

Serializer validation is necessary but not sufficient. lifecycle_fencing, plan checks, share permissions and runtime policy are separate enforcement layers.

Source: src/services/serializers.py, api/*.py, lifecycle/authority.py, revisioning.py.
