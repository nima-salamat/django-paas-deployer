from rest_framework import serializers
from .models import PrivateNetwork, Service, Volume
from plans.serializers import PlanSerializer


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
    service_name = serializers.ReadOnlyField(source="get_service_name")
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
        ]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
        }

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
    network = PrivateNetworkSerializer()
    plan = PlanSerializer()
    storage = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "storage"]

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
            # size can still be changed but quota is validated in validate()
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
        """
        Enforce:
        1. Exclusive ownership (cannot attach to a different service if already owned).
        2. Plan storage quota when service is set / changed / size grows.
        """
        attrs = super().validate(attrs)
        request = self.context.get("request")
        instance = self.instance

        service = attrs.get("service", getattr(instance, "service", None) if instance else None)
        size_mb = attrs.get(
            "size_mb",
            getattr(instance, "size_mb", None) if instance else None,
        )

        # Ownership conflict
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
            # Resolve Service instance if we only got an id
            if not hasattr(service, "can_allocate_storage"):
                from .models import Service as ServiceModel

                try:
                    service = ServiceModel.objects.select_related("plan").get(pk=service)
                except ServiceModel.DoesNotExist:
                    raise serializers.ValidationError({"service": "Service not found."})

            # Same user
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
        # user is set by the view
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # If service is explicitly set to null → detach
        if "service" in validated_data and validated_data["service"] is None:
            instance.service = None
            instance.service_attachments = {}
            # size may still change while unused (no quota)
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
            # New exclusive attach
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
