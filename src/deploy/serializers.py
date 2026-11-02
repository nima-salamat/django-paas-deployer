from rest_framework import serializers
import re
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, InterfaceError, ProgrammingError, transaction
import logging

from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS
from deployments.common.config import sanitize_tenant_config, validate_tenant_config
from .models import Deploy, DeployLog
from .naming import allocate_deploy_name, normalize_deploy_name

logger = logging.getLogger(__name__)

def _integrity_constraint_name(exc: IntegrityError) -> str:
    """Return PostgreSQL's named constraint when the driver exposes it."""
    cause = getattr(exc, "__cause__", None) or getattr(exc, "orig", None)
    diag = getattr(cause, "diag", None)
    return str(getattr(diag, "constraint_name", "") or "").strip()
class MaskedDBConfigField(serializers.JSONField):
    """Expose sensitive deployment config only to explicitly authorized viewers.

    Secrets can occur in nested environment dictionaries, catalog settings and
    database connection strings. Redaction therefore applies recursively and
    does not depend on the workload platform.
    """

    _SENSITIVE_TOKENS = (
        "password", "secret", "token", "private_key", "api_key", "apikey",
        "authorization", "credential", "dsn", "database_url", "connection_string",
    )
    _URL_CREDENTIALS = re.compile(
        r"(?i)([a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s/@]+(@)"
    )
    _INLINE_PASSWORD = re.compile(
        r"(?i)(\b(?:password|passwd|pwd)\s*=\s*)('[^']*'|\"[^\"]*\"|[^;\s]+)"
    )

    @classmethod
    def _sensitive_key(cls, key):
        lowered = str(key).strip().lower().replace("-", "_")
        return lowered in SENSITIVE_CONFIG_KEYS or any(
            token in lowered for token in cls._SENSITIVE_TOKENS
        )

    @classmethod
    def _redact(
        cls,
        value,
        secret_values=(),
        *,
        allow_top_level_db_credentials=False,
        path=(),
    ):
        if isinstance(value, dict):
            output = {}
            for key, item in value.items():
                lowered = str(key).strip().lower().replace("-", "_")
                allow_db_field = (
                    allow_top_level_db_credentials
                    and not path
                    and lowered in {"password", "root_password", "username"}
                )
                if cls._sensitive_key(key) and not allow_db_field:
                    output[key] = "[REDACTED]"
                else:
                    output[key] = cls._redact(
                        item,
                        secret_values,
                        allow_top_level_db_credentials=allow_top_level_db_credentials,
                        path=(*path, str(key)),
                    )
            return output
        if isinstance(value, (list, tuple)):
            return [
                cls._redact(
                    item,
                    secret_values,
                    allow_top_level_db_credentials=allow_top_level_db_credentials,
                    path=(*path, str(index)),
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, str):
            cleaned = cls._URL_CREDENTIALS.sub(r"\1[REDACTED]\2", value)
            cleaned = cls._INLINE_PASSWORD.sub(r"\1[REDACTED]", cleaned)
            for secret in secret_values:
                if secret:
                    cleaned = cleaned.replace(str(secret), "[REDACTED]")
            return cleaned
        return value

    def to_representation(self, value):
        data = super().to_representation(value)
        if not isinstance(data, dict):
            return data

        request = self.context.get("request")
        parent = getattr(self, "parent", None)
        deploy = getattr(parent, "instance", None) if parent is not None else None
        service = getattr(deploy, "service", None) if deploy is not None else None
        user = getattr(request, "user", None) if request is not None else None

        is_owner = bool(
            user is not None
            and service is not None
            and getattr(user, "is_authenticated", False)
            and str(service.user_id) == str(getattr(user, "id", ""))
        )
        if is_owner:
            return data

        # Database-credential permission is narrower than general Secret
        # access. It may expose only top-level DB username/password fields;
        # nested app env, DSNs, tokens and catalog secrets remain masked.
        allow_top_level_db_credentials = False
        if (
            user is not None
            and service is not None
            and getattr(user, "is_authenticated", False)
            and str(data.get("platform") or "").strip().lower() in DB_PLATFORMS
        ):
            try:
                from services.api.sharing import user_can_access_service
                allowed, share = user_can_access_service(
                    service, user, action="can_view_db_credentials"
                )
                allow_top_level_db_credentials = bool(
                    allowed and share and share.allows("can_view_db_credentials")
                )
            except Exception:
                allow_top_level_db_credentials = False

        secret_values = set()
        try:
            binding = getattr(service, "application_binding", None)
            instance = getattr(binding, "instance", None)
            secret_config = getattr(instance, "secret_config", {}) or {}
            if isinstance(secret_config, dict):
                secret_values = {
                    str(item) for item in secret_config.values()
                    if item not in (None, "")
                }
        except Exception:
            secret_values = set()

        return self._redact(
            data,
            secret_values,
            allow_top_level_db_credentials=allow_top_level_db_credentials,
        )


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
        """Validate permissions/warnings and enforce revision immutability."""
        if self.instance is not None and getattr(self.instance, "revision_id", None):
            changed = set(attrs) & {"service", "version", "zip_file", "config"}
            if changed:
                raise serializers.ValidationError({
                    "revision": (
                        "This deployment already has an immutable service revision. "
                        "Create a new deployment instead of changing its executable configuration."
                    )
                })
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
                constraint = _integrity_constraint_name(exc)
                logger.error(
                    "Deploy create IntegrityError constraint=%s detail=%s",
                    constraint or "?",
                    exc,
                )
                if constraint == "deploy_deploy_name_key":
                    raise serializers.ValidationError(
                        {
                            "name": (
                                "Deployment database schema is outdated. "
                                "Apply migration deploy.0017_drop_legacy_deploy_name_unique."
                            ),
                            "code": "deployment_schema_out_of_date",
                        }
                    )
                if constraint == "uniq_deploy_service_name":
                    raise serializers.ValidationError(
                        {"name": "A deploy with this name already exists for this service."}
                    )
                raise serializers.ValidationError(
                    {
                        "error": "Deployment could not be created because of a database integrity error.",
                        "code": "deployment_integrity_error",
                        "constraint": constraint or None,
                    }
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
            constraint = _integrity_constraint_name(exc)
            logger.error(
                "Deploy update IntegrityError constraint=%s detail=%s",
                constraint or "?",
                exc,
            )
            if constraint == "deploy_deploy_name_key":
                raise serializers.ValidationError(
                    {
                        "name": (
                            "Deployment database schema is outdated. "
                            "Apply migration deploy.0017_drop_legacy_deploy_name_unique."
                        ),
                        "code": "deployment_schema_out_of_date",
                    }
                )
            if constraint == "uniq_deploy_service_name":
                raise serializers.ValidationError(
                    {"name": "A deploy with this name already exists for this service."}
                )
            raise serializers.ValidationError(
                {
                    "error": "Deployment could not be updated because of a database integrity error.",
                    "code": "deployment_integrity_error",
                    "constraint": constraint or None,
                }
            )
        return instance
