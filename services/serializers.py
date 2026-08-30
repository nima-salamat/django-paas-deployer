from rest_framework import serializers
from django.conf import settings as django_settings

from .models import PrivateNetwork, Service, Volume
from plans.serializers import PlanSerializer


def _deployment_domain() -> str:
    """
    Public suffix for service hosts, e.g. deploy.echonode.website
    From Django settings.DEPLOYMENT_DOMAIN (env DEPLOYMENT_DOMAIN).
    """
    raw = getattr(django_settings, "DEPLOYMENT_DOMAIN", None) or ""
    return str(raw).strip().lstrip(".").rstrip(".")


def _service_docker_label(obj: Service) -> str | None:
    try:
        return obj.get_docker_service_name()
    except Exception:
        return None


def _service_host(obj: Service) -> str | None:
    label = _service_docker_label(obj)
    if not label:
        return None
    domain = _deployment_domain()
    if not domain or domain.lower() in ("local", "localhost"):
        # Still return label.domain if domain is set; for "local" keep full form
        if not domain:
            return label
    return f"{label}.{domain}"


class PrivateNetworkSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    connected_services = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PrivateNetwork
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "connected_services"]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
        }

    def get_connected_services(self, obj):
        try:
            return obj.Service.count()
        except Exception:
            return 0

    def get_fields(self):
        fields = super().get_fields()
        if self.instance:
            fields["name"].read_only = True
        return fields


class ServiceSerializer(serializers.ModelSerializer):
    # Docker container / DNS label: app-<id8>-<name>
    service_name = serializers.SerializerMethodField(read_only=True)
    # Full public host: <service_name>.<DEPLOYMENT_DOMAIN>
    service_host = serializers.SerializerMethodField(read_only=True)
    storage = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "selected_deploy_at",
            "deployed_at",
            "storage",
            "service_name",
            "service_host",
        ]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
        }

    def get_service_name(self, obj):
        return _service_docker_label(obj)

    def get_service_host(self, obj):
        return _service_host(obj)

    def get_storage(self, obj):
        try:
            return obj.storage_quota_summary()
        except Exception:
            return {
                "quota_mb": 0,
                "used_mb": 0,
                "remaining_mb": 0,
                "quota_gb": 0,
                "used_gb": 0,
                "remaining_gb": 0,
            }

    def get_fields(self):
        fields = super().get_fields()
        if self.instance:
            fields["name"].read_only = True
        return fields


class GetServiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    network = PrivateNetworkSerializer(allow_null=True, required=False)
    plan = PlanSerializer(allow_null=True, required=False)
    service_name = serializers.SerializerMethodField(read_only=True)
    service_host = serializers.SerializerMethodField(read_only=True)
    storage = serializers.SerializerMethodField(read_only=True)
    user_username = serializers.SerializerMethodField(read_only=True)
    user_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "storage",
            "service_name",
            "service_host",
            "user_username",
            "user_info",
        ]

    def get_service_name(self, obj):
        return _service_docker_label(obj)

    def get_service_host(self, obj):
        return _service_host(obj)

    def get_user_username(self, obj):
        try:
            return getattr(obj.user, "username", None)
        except Exception:
            return None

    def get_user_info(self, obj):
        try:
            u = obj.user
            if not u:
                return None
            return {
                "id": str(getattr(u, "pk", "") or ""),
                "username": getattr(u, "username", None),
                "email": getattr(u, "email", None),
            }
        except Exception:
            return None

    def get_storage(self, obj):
        try:
            return obj.storage_quota_summary()
        except Exception:
            return {
                "quota_mb": 0,
                "used_mb": 0,
                "remaining_mb": 0,
                "quota_gb": 0,
                "used_gb": 0,
                "remaining_gb": 0,
            }


class VolumeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    service_name = serializers.SerializerMethodField(read_only=True)
    service_status = serializers.SerializerMethodField(read_only=True)
    is_unused = serializers.SerializerMethodField(read_only=True)
    attached_services = serializers.SerializerMethodField(read_only=True)
    attached_services_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Volume
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "user",
            "service_name",
            "service_status",
            "is_unused",
            "attached_services",
            "attached_services_count",
            "service_attachments",
        ]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "service": {"required": False, "allow_null": True},
        }

    def get_fields(self):
        fields = super().get_fields()
        if self.instance:
            fields["name"].read_only = True
        return fields

    def get_service_name(self, obj):
        return obj.service.name if obj.service else None

    def get_service_status(self, obj):
        return obj.service.status if obj.service else "unused"

    def get_is_unused(self, obj):
        return obj.service_id is None

    def get_attached_services(self, obj):
        if not obj.service_id:
            return []
        s = obj.service
        att = (obj.service_attachments or {}).get(str(s.id), {})
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "bind": att.get("bind", obj.default_bind or ""),
                "mode": att.get("mode", obj.default_mode or "rw"),
            }
        ]

    def get_attached_services_count(self, obj):
        return 1 if obj.service_id else 0

    def validate_size_mb(self, value):
        if value is None or int(value) <= 0:
            raise serializers.ValidationError("Volume size must be greater than zero.")
        return int(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        instance = self.instance

        service = attrs.get("service", getattr(instance, "service", None) if instance else None)
        size_mb = attrs.get(
            "size_mb",
            getattr(instance, "size_mb", None) if instance else None,
        )

        if instance and instance.service_id and service is not None:
            if str(instance.service_id) != str(getattr(service, "pk", service)):
                raise serializers.ValidationError(
                    {
                        "service": (
                            "This volume is already attached to another service. "
                            "Volumes cannot be shared between services. "
                            "Detach it first."
                        )
                    }
                )

        if service is not None and size_mb is not None:
            if not hasattr(service, "can_allocate_storage"):
                from .models import Service as ServiceModel

                try:
                    service = ServiceModel.objects.select_related("plan").get(pk=service)
                except ServiceModel.DoesNotExist:
                    raise serializers.ValidationError({"service": "Service not found."})

            if request and str(service.user_id) != str(request.user.id):
                raise serializers.ValidationError(
                    {"service": "Selected service does not belong to the authenticated user."}
                )

            exclude_id = instance.pk if instance else None
            ok, msg = service.can_allocate_storage(size_mb, exclude_volume_id=exclude_id)
            if not ok:
                raise serializers.ValidationError({"size_mb": msg})

        return attrs

    def create(self, validated_data):
        service = validated_data.pop("service", None)
        instance = super().create(validated_data)

        if service is not None:
            bind = instance.default_bind or "/data"
            mode = instance.default_mode or "rw"
            instance.attach_to_service(service, bind=bind, mode=mode)

        return instance

    def update(self, instance, validated_data):
        if "service" in validated_data and validated_data["service"] is None:
            instance.service = None
            instance.service_attachments = {}
            if "size_mb" in validated_data:
                instance.size_mb = validated_data["size_mb"]
            if "default_bind" in validated_data:
                instance.default_bind = validated_data["default_bind"]
            if "default_mode" in validated_data:
                instance.default_mode = validated_data["default_mode"]
            instance.save()
            return instance

        service = validated_data.get("service")
        if service is not None and (
            not instance.service_id or str(instance.service_id) != str(service.pk)
        ):
            bind = validated_data.get("default_bind") or instance.default_bind or "/data"
            mode = validated_data.get("default_mode") or instance.default_mode or "rw"
            if "size_mb" in validated_data:
                instance.size_mb = validated_data["size_mb"]
            if "default_bind" in validated_data:
                instance.default_bind = validated_data["default_bind"]
            if "default_mode" in validated_data:
                instance.default_mode = validated_data["default_mode"]
            instance.attach_to_service(service, bind=bind, mode=mode)
            return instance

        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Service Sharing
# ---------------------------------------------------------------------------

from .models import ServiceShare, ServiceShareEvent
from services.share_permissions import DEFAULT_SHARE_RULES, normalize_rules, full_owner_rules, RULE_LABELS


# DEFAULT_SHARE_RULES imported from services.share_permissions


class ServiceShareSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    service_id = serializers.CharField(source="service_id", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    service_status = serializers.CharField(source="service.status", read_only=True)
    shared_by_id = serializers.CharField(source="shared_by_id", read_only=True)
    shared_by_username = serializers.SerializerMethodField()
    group_id = serializers.CharField(source="group_id", read_only=True, allow_null=True)
    group_title = serializers.SerializerMethodField()
    target_user_id = serializers.CharField(source="target_user_id", read_only=True, allow_null=True)
    target_username = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = ServiceShare
        fields = [
            "id",
            "service_id",
            "service_name",
            "service_status",
            "group_id",
            "group_title",
            "target_user_id",
            "target_username",
            "shared_by_id",
            "shared_by_username",
            "rules",
            "is_active",
            "note",
            "expires_at",
            "admin_only",
            "preset",
            "is_owner",
            "my_permissions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "service_id",
            "service_name",
            "service_status",
            "shared_by_id",
            "shared_by_username",
            "group_title",
            "target_username",
            "is_owner",
            "my_permissions",
            "created_at",
            "updated_at",
        ]

    def get_shared_by_username(self, obj):
        u = getattr(obj, "shared_by", None)
        return getattr(u, "username", None) or getattr(u, "email", None) or str(obj.shared_by_id)

    def get_group_title(self, obj):
        g = getattr(obj, "group", None)
        if not g:
            return None
        return g.title or str(g.public_id)

    def get_target_username(self, obj):
        u = getattr(obj, "target_user", None)
        if not u:
            return None
        return getattr(u, "username", None) or getattr(u, "email", None) or str(obj.target_user_id)

    def get_is_owner(self, obj):
        request = self.context.get("request")
        if not request or not getattr(request, "user", None):
            return False
        return str(obj.shared_by_id) == str(request.user.id)

    def get_my_permissions(self, obj):
        """Rules the current user can exercise on this shared service."""
        request = self.context.get("request")
        if not request or not getattr(request, "user", None):
            return {}
        # Owner always has full control
        if str(obj.shared_by_id) == str(request.user.id):
            return full_owner_rules()
        # Per-member override for group shares
        if obj.group_id:
            try:
                from services.models import ServiceShareMember
                mem = ServiceShareMember.objects.filter(share=obj, user=request.user).first()
                if mem is not None:
                    if not mem.is_enabled:
                        return {k: False for k in DEFAULT_SHARE_RULES}
                    return normalize_rules(mem.rules or {})
            except Exception:
                pass
        return normalize_rules(obj.rules or DEFAULT_SHARE_RULES)


class ServiceShareCreateSerializer(serializers.Serializer):
    service_id = serializers.UUIDField(required=True)
    group_id = serializers.IntegerField(required=False, allow_null=True)
    target_user_id = serializers.UUIDField(required=False, allow_null=True)
    rules = serializers.DictField(required=False, default=dict)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    admin_only = serializers.BooleanField(required=False, default=False)
    preset = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")

    def validate(self, attrs):
        group_id = attrs.get("group_id")
        target_user_id = attrs.get("target_user_id")
        if bool(group_id) == bool(target_user_id):
            raise serializers.ValidationError(
                _("Exactly one of group_id or target_user_id must be provided.")
            )
        rules = attrs.get("rules") or {}
        if not isinstance(rules, dict):
            raise serializers.ValidationError({"rules": _("Must be a JSON object.")})
        preset = (attrs.get("preset") or "").strip().lower()
        if preset:
            from services.share_permissions import RULE_PRESETS
            if preset not in RULE_PRESETS:
                raise serializers.ValidationError({"preset": _("Unknown preset.")})
            attrs["rules"] = dict(RULE_PRESETS[preset])
            attrs["preset"] = preset
        else:
            attrs["rules"] = normalize_rules(rules)
        return attrs


class ServiceShareUpdateSerializer(serializers.Serializer):
    rules = serializers.DictField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
    is_active = serializers.BooleanField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    admin_only = serializers.BooleanField(required=False)
    preset = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def validate_rules(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Must be a JSON object."))
        return normalize_rules(value)


class ServiceShareEventSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = ServiceShareEvent
        fields = [
            "id",
            "share",
            "actor",
            "actor_username",
            "action",
            "message",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_username(self, obj):
        u = getattr(obj, "actor", None)
        if not u:
            return None
        return getattr(u, "username", None) or getattr(u, "email", None) or str(obj.actor_id)
