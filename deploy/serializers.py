from rest_framework import serializers
from django.db import OperationalError, InterfaceError, ProgrammingError
import logging

from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS
from .models import Deploy, DeployLog

logger = logging.getLogger(__name__)


class MaskedDBConfigField(serializers.JSONField):
    """JSONField that strips sensitive DB credentials on read, but accepts full dict on write."""
    def to_representation(self, value):
        # Call parent to get the normal dict representation
        data = super().to_representation(value)
        if not isinstance(data, dict):
            return data
        platform = data.get("platform") or ""
        if platform in DB_PLATFORMS:
            # Remove sensitive keys before sending to client
            return {k: v for k, v in data.items() if k not in SENSITIVE_CONFIG_KEYS}
        return data


class DeployLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeployLog
        fields = [
            "id", "deploy", "service", "stage", "event_type", "level",
            "message", "progress", "details", "exception_type", "traceback",
            "created_at",
        ]
        read_only_fields = fields


class DeploySerializer(serializers.ModelSerializer):
    # Use the writable field – no more SerializerMethodField
    config = MaskedDBConfigField()

    recent_logs = serializers.SerializerMethodField()

    class Meta:
        model = Deploy
        fields = [
            "id", "name", "service", "version", "zip_file",
            "config",
            "started_at", "completed_at", "status", "stage", "progress",
            "status_message", "error_message", "rollback_status",
            "health_status", "container_status", "image_status",
            "volume_status", "network_status",
            "recent_logs", "created_at", "updated_at",
        ]
        read_only_fields = [
            "started_at", "completed_at", "status", "stage", "progress",
            "status_message", "error_message", "rollback_status",
            "health_status", "container_status", "image_status",
            "volume_status", "network_status",
            "recent_logs", "created_at", "updated_at", "updated_file_at",
        ]

    def get_recent_logs(self, obj):
        from django.conf import settings

        try:
            logs = (
                DeployLog.objects
                .using(settings.DEPLOYMENT_LOG_DB_ALIAS)
                .filter(deploy_id=obj.pk)
                .order_by("-created_at")[:20]
            )
            return DeployLogSerializer(reversed(list(logs)), many=True).data
        except (OperationalError, InterfaceError, ProgrammingError) as exc:
            # A dedicated deployment-log DB must never make the primary
            # deploy/service API unavailable. Surface an empty log list and
            # leave the details in server logs rather than leaking DB errors.
            logger.warning(
                "Deployment log database unavailable for deploy %s: %s",
                getattr(obj, "pk", None),
                exc,
            )
            return []

    def create(self, validated_data):
        request = self.context.get("request")
        instance = Deploy(**validated_data)
        if request and (request.user.is_superuser or request.user.is_staff):
            instance.skip_zip_size_limit = True
        instance.save()
        return instance

    def update(self, instance, validated_data):
        request = self.context.get("request")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if request and (request.user.is_superuser or request.user.is_staff):
            instance.skip_zip_size_limit = True
        instance.save()
        return instance

