from rest_framework import serializers
from .catalog import ApplicationCatalog, redacted_definition
from .models import ApplicationInstance


class ApplicationInstanceSerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationInstance
        fields = (
            "id", "name", "catalog_id", "definition_version", "software_version", "variant_id",
            "status", "stage", "cancel_requested", "config", "error_code", "error_message", "created_at",
            "updated_at", "deployed_at", "services",
        )

    def get_config(self, obj):
        out = dict(obj.config or {})
        out["secrets_configured"] = sorted((obj.secret_config or {}).keys())
        return out

    def get_services(self, obj):
        rows = []
        for binding in obj.services.select_related("service", "deploy").all():
            deploy = binding.deploy
            rows.append({
                "key": binding.service_key,
                "service_id": str(binding.service_id),
                "service_name": binding.service.name,
                "deploy_id": str(deploy.pk),
                "status": deploy.status,
                "stage": deploy.stage,
                "status_message": deploy.status_message,
                "error_message": deploy.error_message if deploy.status == "failed" else "",
            })
        return rows


def catalog_listing():
    return [redacted_definition(d) for d in ApplicationCatalog.definitions()]
