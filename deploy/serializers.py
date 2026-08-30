from rest_framework import serializers
from django.db import OperationalError, InterfaceError, ProgrammingError
import logging

from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS
from deployments.common.config import sanitize_tenant_config
from .models import Deploy, DeployLog

logger = logging.getLogger(__name__)


class MaskedDBConfigField(serializers.JSONField):
    """JSONField that strips sensitive DB credentials on read, but accepts full dict on write.

    Secrets are visible only to the service owner or a share recipient with
    can_view_db_credentials=True.
    """
    def to_representation(self, value):
        data = super().to_representation(value)
        if not isinstance(data, dict):
            return data
        platform = data.get("platform") or ""
        if platform not in DB_PLATFORMS:
            return data

        request = self.context.get("request")
        parent = getattr(self, "parent", None)
        deploy = getattr(parent, "instance", None) if parent is not None else None
        # list serializer: instance may be on parent
        if deploy is None and parent is not None:
            deploy = getattr(parent, "instance", None)

        allow_secrets = False
        user = getattr(request, "user", None) if request else None
        service = getattr(deploy, "service", None) if deploy is not None else None
        if user and service is not None:
            if str(service.user_id) == str(user.id):
                allow_secrets = True
            else:
                try:
                    from services.api.sharing import user_can_access_service
                    ok, share = user_can_access_service(
                        service, user, action="can_view_db_credentials"
                    )
                    allow_secrets = bool(ok and share and share.allows("can_view_db_credentials"))
                except Exception:
                    allow_secrets = False

        if allow_secrets:
            return data
        return {k: v for k, v in data.items() if k not in SENSITIVE_CONFIG_KEYS}


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
            "id", "name", "service", "created_by", "version", "zip_file",
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
            "recent_logs", "created_at", "updated_at", "updated_file_at", "created_by",
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

    def validate(self, attrs):
        """Enforce share can_deploy_add on create (non-owners)."""
        request = self.context.get("request")
        if request is None or self.instance is not None:
            return attrs
        service = attrs.get("service")
        user = getattr(request, "user", None)
        if service is None or user is None or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"service": "Service is required."})
        if str(service.user_id) == str(user.id):
            return attrs
        from services.api.sharing import user_can_access_service
        allowed, share = user_can_access_service(service, user, action="can_deploy_add")
        if not allowed:
            raise serializers.ValidationError(
                {
                    "service": "You do not have permission to add deploys on this shared service.",
                    "code": "share_permission_denied",
                    "action": "can_deploy_add",
                }
            )
        return attrs


    def create(self, validated_data):
        request = self.context.get("request")
        service = validated_data.get("service")
        user = getattr(request, "user", None) if request else None
        if service is not None and user is not None and str(service.user_id) != str(user.id):
            from services.api.sharing import user_can_access_service
            allowed, _ = user_can_access_service(service, user, action="can_deploy_add")
            if not allowed:
                raise serializers.ValidationError(
                    {
                        "service": "You do not have permission to add deploys on this shared service.",
                        "code": "share_permission_denied",
                        "action": "can_deploy_add",
                    }
                )
        if "config" in validated_data:
            validated_data["config"] = sanitize_tenant_config(validated_data["config"])
        instance = Deploy(**validated_data)
        if request and (request.user.is_superuser or request.user.is_staff):
            instance.skip_zip_size_limit = True
        instance.save()
        return instance

    def update(self, instance, validated_data):
        request = self.context.get("request")
        for attr, value in validated_data.items():
            if attr == "config":
                value = sanitize_tenant_config(value)
            setattr(instance, attr, value)
        if request and (request.user.is_superuser or request.user.is_staff):
            instance.skip_zip_size_limit = True
        instance.save()
        return instance
