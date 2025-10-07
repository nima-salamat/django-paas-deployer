from rest_framework import serializers
from .models import PrivateNetwork, Container, Volume
from plans.serializers import PlanSerializer
class PrivateNetworkSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    class Meta:
        model = PrivateNetwork
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class ContainerSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    network = PrivateNetworkSerializer()
    plan = PlanSerializer()
    class Meta:
        model = Container
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class VolumeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="pk", read_only=True)
    class Meta:
        model = Volume
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]