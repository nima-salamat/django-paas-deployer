from rest_framework import serializers
from .models import PrivateNetwork, Service, Volume
from plans.serializers import PlanSerializer


class PrivateNetworkSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    class Meta:
        model = PrivateNetwork
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "name" : {"required": True, "allow_blank": False},
        }

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
        read_only_fields = ["id", "created_at", "updated_at"]
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
    class Meta:
        model = Volume
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "name" : {"required": True, "allow_blank": False},
        }
        
    def get_fields(self):
        fields = super().get_fields()
        if self.instance:
            fields["name"].read_only = True

        return fields
