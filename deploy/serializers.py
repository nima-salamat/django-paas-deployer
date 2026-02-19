from rest_framework import serializers
from .models import Deploy

class DeploySerializer(serializers.ModelSerializer):
    class Meta:
        model = Deploy
        fields = [
            "id",
            "name",
            "service",
            "version",
            "zip_file",
            "config",
            "started_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["started_at", "created_at", "updated_at", "updated_file_at"]
