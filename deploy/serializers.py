from rest_framework import serializers

from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS

from .models import Deploy, DeployLog


class DeployLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeployLog
        fields = [
            "id",
            "deploy",
            "service",
            "stage",
            "event_type",
            "level",
            "message",
            "progress",
            "details",
            "exception_type",
            "traceback",
            "created_at",
        ]
        read_only_fields = fields


class DeploySerializer(serializers.ModelSerializer):
    recent_logs = serializers.SerializerMethodField()
    # config is overridden so sensitive credential keys (password, username,
    # root_password) are never returned in read responses for DB deploys.
    config = serializers.SerializerMethodField()

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

    def get_config(self, obj):
        """
        Return the config dict with sensitive credential keys stripped for DB
        platforms.  For non-DB platforms the full config is returned as-is.

        Stripped keys: password, root_password, username.
        These values are write-only — they are stored server-side and injected
        at container runtime but should never travel back to the client.
        """
        cfg = obj.config
        if not isinstance(cfg, dict):
            return cfg
        platform = cfg.get("platform") or ""
        if platform not in DB_PLATFORMS:
            return cfg
        return {k: v for k, v in cfg.items() if k not in SENSITIVE_CONFIG_KEYS}

    def get_recent_logs(self, obj):
        from django.conf import settings

        logs = (
            DeployLog.objects
            .using(settings.DEPLOYMENT_LOG_DB_ALIAS)
            .filter(deploy_id=obj.pk)
            .order_by("-created_at")[:20]
        )
        return DeployLogSerializer(reversed(list(logs)), many=True).data
