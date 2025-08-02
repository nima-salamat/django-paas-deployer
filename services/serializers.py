from rest_framework import serializers
from .models import PrivateNetwork, Service

class PrivateNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivateNetwork
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]