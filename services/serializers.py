from rest_framework import serializers
from .models import PrivateNetwork, Container, Volume


class PrivateNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivateNetwork
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class ContainerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Container
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class VolumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Volume
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]