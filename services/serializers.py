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
            "name" : {"required": True, "allow_blank": False},
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
    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "selected_deploy_at", "deployed_at"]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
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
    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class VolumeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    service_name = serializers.SerializerMethodField(read_only=True)
    service_status = serializers.SerializerMethodField(read_only=True)
    is_unused = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Volume
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "service_name", "service_status", "is_unused"]
        extra_kwargs = {
            "name" : {"required": True, "allow_blank": False},
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
        return obj.service is None
