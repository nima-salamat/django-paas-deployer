# services serializers

## PrivateNetworkSerializer
Model: PrivateNetwork. ModelSerializer uses all model fields; id, created_at, updated_at and connected_services are read-only. connected_services is derived from current Service relations. Owner/queryset scope remains the authorization boundary.

## ServiceSerializer
Model: Service. ModelSerializer uses all model fields. service_name, service_host and storage are derived fields. validate() rejects incompatible plan changes during protected lifecycle states; model/domain validation remains authoritative after serializer validation. Accepted desired configuration must later become a ServiceRevision before execution.

## GetServiceSerializer
Model: Service. Read projection using all model fields plus derived service_name, service_host, user_username, user_info and storage. It never grants object access; ViewSet/queryset resolution does.

## VolumeSerializer
Model: Volume. ModelSerializer uses all model fields. Derived fields are service_name, service_status, is_unused, attached_services and attached_services_count. validate_size_mb enforces positive size; validate() enforces Service ownership/quota. create/update use Volume domain operations so service attachment/release cannot bypass lifecycle invariants.

## ServiceShareSerializer
Read representation of ServiceShare. Fields: id, service_id, service_name, service_status, service_platform, service_plan_type, service, group_id, group_title, target_user_id, target_username, shared_by_id, shared_by_username, rules, is_active, note, expires_at, admin_only, preset, is_owner, my_permissions, created_at, updated_at. SerializerMethodField values are viewer-sensitive. my_permissions uses owner rules, group-member overrides or normalized share rules.

## ServiceShareCreateSerializer
Input fields: service_id required UUID; exactly one of group_id/target_user_id; rules object default {}; note optional max 255; expires_at nullable; admin_only default false; preset optional. validate() rejects both/neither target, non-object rules and unknown presets, and normalizes the resulting rules.

## ServiceShareUpdateSerializer
Input fields: rules, note, is_active, expires_at, admin_only, preset. validate_rules requires an object and normalizes it. It is an owner-controlled policy update, not a generic model update.

## ServiceShareEventSerializer
Read-only ServiceShareEvent representation: id, share, actor, actor_username, action, message, metadata, created_at. actor_username is derived. Events are audit history, never permission grants.

## Validation placement
request -> authentication/object/share permission -> serializer field/cross-field validation -> model/domain constraints -> lifecycle/revision policy -> on_commit task where external work is required.

Source: src/services/serializers.py and src/services/api/*.py.