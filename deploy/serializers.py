from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, InterfaceError, ProgrammingError, transaction
import logging

from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS
from deployments.common.config import sanitize_tenant_config, validate_tenant_config
from .models import Deploy, DeployLog
from .naming import allocate_deploy_name, normalize_deploy_name

logger = logging.getLogger(__name__)


def _unique_deploy_name(service, requested_name):
    """Allocate a deployment name unique within one service."""
    base = str(requested_name or getattr(service, "name", "deploy") or "deploy").strip()[:50]
    base = base or "deploy"
    candidate = base
    index = 2
    while Deploy.objects.filter(service=service, name=candidate).exists():
        suffix = f"-{index}"
        candidate = f"{base[:50 - len(suffix)]}{suffix}"
        index += 1
    return candidate


class MaskedDBConfigField(serializers.JSONField):
    """JSONField that strips sensitive DB credentials on read, but accepts full dict on write.

    Secrets are visible only to the service owner or a share recipient with
    can_view_db_credentials=True.
    """
    def to_representation(self, value):
        data = super().to_representation(value)
        if not isinstance(data, dict):
            return data
        request = self.context.get("request")

        # Catalog-managed application deploys may contain generated secrets in
        # their environment configuration even when their platform is Docker
        # rather than a DB platform.  Never expose those values through the
        # normal deploy API representation.
        if data.get("catalog_managed"):
            sensitive_tokens = ("password", "secret", "token", "private_key", "api_key", "signing_key")
            cleaned = dict(data)
            secret_values = set()
            parent = getattr(self, "parent", None)
            deploy = getattr(parent, "instance", None) if parent is not None else None
            try:
                binding = getattr(getattr(deploy, "service", None), "application_binding", None)
                instance = getattr(binding, "instance", None)
                secret_values = {str(value) for value in (getattr(instance, "secret_config", {}) or {}).values() if value not in (None, "")}
            except Exception:
                secret_values = set()

            def redact(value):
                if isinstance(value, dict):
                    return {key: redact(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [redact(item) for item in value]
                if isinstance(value, str):
                    out = value
                    for secret in secret_values:
                        if secret:
                            out = out.replace(secret, "[REDACTED]")
                    return out
                return value

            for key in list(cleaned):
                lowered = str(key).lower()
                if key in SENSITIVE_CONFIG_KEYS or any(token in lowered for token in sensitive_tokens):
                    cleaned[key] = "[REDACTED]"
            return redact(cleaned)

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


class DeploymentZipField(serializers.FileField):
    """Write ZIP uploads normally, but return the authenticated download URL on read."""

    def to_representation(self, value):
        if not value:
            return None
        serializer = getattr(self, "parent", None)
        deploy = getattr(serializer, "instance", None)
        deploy_id = getattr(deploy, "pk", None)
        if deploy_id:
            path = f"/deploy/{deploy_id}/download/"
            request = self.context.get("request")
            return request.build_absolute_uri(path) if request is not None else path
        return super().to_representation(value)


class DeploySerializer(serializers.ModelSerializer):
    zip_file = DeploymentZipField(required=False, allow_null=True)
    config = MaskedDBConfigField()

    recent_logs = serializers.SerializerMethodField()

    class Meta:
        model = Deploy
        fields = [
            "id", "name", "service", "created_by", "version", "zip_file",
            "revision", "config",
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
            "recent_logs", "created_at", "updated_at", "updated_file_at", "created_by", "revision",
        ]

    def get_recent_logs(self, obj):
        from django.conf import settings

        try:
            alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "deployment_logs"
            logs = (
                DeployLog.objects
                .using(alias)
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
        except Exception as exc:
            logger.warning(
                "get_recent_logs failed for deploy %s: %s",
                getattr(obj, "pk", None),
                exc,
            )
            return []

    def validate(self, attrs):
        # Once execution has produced a revision, the Deploy is no longer a
        # mutable configuration object. Create a new Deploy to produce a new
        # immutable ServiceRevision.
        if self.instance is not None and getattr(self.instance, "revision_id", None):
            changed = set(attrs) & {"service", "version", "zip_file", "config"}
            if changed:
                raise serializers.ValidationError({
                    "revision": (
                        "This deployment already has an immutable service revision. "
                        "Create a new deployment instead of changing its executable configuration."
                    )
                })
        """Validate permissions, immutable revisions, and scoped names."""
        Create requests may reuse a deployment name; the create path allocates
        a unique suffix. Existing deployments keep strict name uniqueness when
        renamed so an update cannot silently change identity.
        """
        attrs = super().validate(attrs)
        request = self.context.get("request")
        service = attrs.get("service") or getattr(self.instance, "service", None)
        name = normalize_deploy_name(
            attrs.get("name") or getattr(self.instance, "name", ""),
            fallback="deploy",
        )
        if "name" in attrs:
            attrs["name"] = name

        if request is not None and self.instance is None:
            user = getattr(request, "user", None)
            if service is None or user is None or not getattr(user, "is_authenticated", False):
                raise serializers.ValidationError({"service": "Service is required."})
            if str(service.user_id) != str(user.id):
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
            self._collect_config_warnings(attrs)

        if self.instance is not None and service is not None and name:
            qs = Deploy.objects.filter(service=service, name=name).exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "A deploy with this name already exists for this service."}
                )
        return attrs

    def _collect_config_warnings(self, attrs):
        """Run the tenant-config contract checker and stash the result."""
        try:
            raw_cfg = attrs.get("config")
            report = validate_tenant_config(raw_cfg)
            self._config_warnings = report.get("warnings") or []
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("validate_tenant_config failed: %s", exc)
            self._config_warnings = []


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

        # Lock the service row while choosing the deployment name. This makes
        # successive creates deterministic under normal concurrent requests and
        # keeps the database uniqueness constraint as the final guard.
        with transaction.atomic():
            if service is not None:
                service = service.__class__.objects.select_for_update().get(pk=service.pk)
                validated_data["service"] = service
                validated_data["name"] = allocate_deploy_name(
                    service,
                    validated_data.get("name"),
                )

            instance = Deploy(**validated_data)
            if request and (request.user.is_superuser or request.user.is_staff):
                instance.skip_zip_size_limit = True
            try:
                instance.save()
            except ValidationError as exc:
                detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
                raise serializers.ValidationError(detail)
            except IntegrityError as exc:
                if "deploy_deploy_name_key" in str(exc):
                    logger.error(
                        "Legacy global deploy-name constraint is still present; "
                        "deploy.0017_drop_legacy_deploy_name_unique must be applied: %s",
                        exc,
                    )
                    raise serializers.ValidationError(
                        {
                            "name": (
                                "Deployment database schema is outdated. "
                                "Apply migration deploy.0017_drop_legacy_deploy_name_unique."
                            ),
                            "code": "deployment_schema_out_of_date",
                        }
                    )
                raise serializers.ValidationError(
                    {"name": "A deploy with this name already exists for this service."}
                )
        return instance

    def update(self, instance, validated_data):
        request = self.context.get("request")
        validated_data.pop("service", None)

        for attr, value in validated_data.items():
            if attr == "config":
                value = sanitize_tenant_config(value)
            setattr(instance, attr, value)
        if request and (request.user.is_superuser or request.user.is_staff):
            instance.skip_zip_size_limit = True
        try:
            instance.save()
        except ValidationError as exc:
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
            raise serializers.ValidationError(detail)
        except IntegrityError as exc:
            if "deploy_deploy_name_key" in str(exc):
                logger.error(
                    "Legacy global deploy-name constraint is still present during update; "
                    "deploy.0017_drop_legacy_deploy_name_unique must be applied: %s",
                    exc,
                )
                raise serializers.ValidationError(
                    {
                        "name": (
                            "Deployment database schema is outdated. "
                            "Apply migration deploy.0017_drop_legacy_deploy_name_unique."
                        ),
                        "code": "deployment_schema_out_of_date",
                    }
                )
            raise serializers.ValidationError(
                {"name": "A deploy with this name already exists for this service."}
            )
        return instance
