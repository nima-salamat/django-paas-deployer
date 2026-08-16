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
        return super().create(validated_data)

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
