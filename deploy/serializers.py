from rest_framework import serializers

from .models import Deploy, DeployLog


class DeployLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeployLog
        fields = [
            "id",
            "deploy",
            "service",
            "stage",
            "level",
            "message",
            "progress",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class DeploySerializer(serializers.ModelSerializer):
    recent_logs = serializers.SerializerMethodField()

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
            "completed_at",
            "status",
            "stage",
            "progress",
            "status_message",
            "error_message",
            "rollback_status",
            "health_status",
            "container_status",
            "image_status",
            "volume_status",
            "network_status",
            "recent_logs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "started_at",
            "completed_at",
            "status",
            "stage",
            "progress",
            "status_message",
            "error_message",
            "rollback_status",
            "health_status",
            "container_status",
            "image_status",
            "volume_status",
            "network_status",
            "recent_logs",
            "created_at",
            "updated_at",
            "updated_file_at",
        ]

    def get_recent_logs(self, obj):
        logs = obj.logs.order_by("-created_at")[:20]
        return DeployLogSerializer(reversed(list(logs)), many=True).data
