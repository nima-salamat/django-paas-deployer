from __future__ import annotations

from rest_framework import serializers
from .catalog import ApplicationCatalog, CatalogDefinition
from .models import ApplicationInstance


PUBLIC_VISIBILITY = "public"


def is_public_definition(definition: CatalogDefinition) -> bool:
    source = definition.source.resolve()
    first_party = (source.parent == (definition.source.parent.parent / "first_party")) if source.parent.parent else False
    return (
        str(definition.data.get("visibility") or "internal").strip().lower() == PUBLIC_VISIBILITY
        and first_party
    )


def _display_component_label(value: str) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text.title() or "Managed component"


def _safe_string_list(value) -> list[str]:
    return [str(item) for item in (value or []) if isinstance(item, (str, int, float))]


def _safe_component_list(definition: CatalogDefinition) -> list[dict]:
    raw = definition.data.get("managed_components") or []
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"label": item})
            continue
        if isinstance(item, dict):
            label = item.get("label") or item.get("name")
            if not label:
                continue
            row = {"label": str(label)}
            role = item.get("role")
            if role:
                row["role"] = str(role)
            out.append(row)
    if out:
        return out

    variant = next(iter(definition.variants.values()), {})
    for service in variant.get("services") or []:
        key = str(service.get("key") or "")
        if key:
            out.append({
                "label": _display_component_label(key),
                "role": str(service.get("role") or "app"),
            })
    return out


def _public_field(field: dict) -> dict | None:
    if field.get("user_editable", True) is False:
        return None
    kind = str(field.get("type") or "string")
    item = {
        "id": str(field["id"]),
        "label": str(field.get("label") or _display_component_label(field["id"])),
        "type": kind,
        "required": bool(field.get("required", False)),
    }
    if kind == "choice":
        item["options"] = [str(option) for option in (field.get("options") or [])]
    if "default" in field and kind != "secret":
        item["default"] = field.get("default")
    ui = field.get("ui") or {}
    if isinstance(ui, dict):
        safe_ui = {}
        for key in ("group", "order", "advanced", "placeholder"):
            if key in ui:
                safe_ui[key] = ui[key]
        if safe_ui:
            item["ui"] = safe_ui
    visible_when = field.get("visible_when")
    if isinstance(visible_when, dict):
        condition = {}
        for key in ("field", "equals", "not_equals"):
            if key in visible_when:
                condition[key] = visible_when[key]
        if condition:
            item["visible_when"] = condition
    return item


def public_catalog_definition(definition: CatalogDefinition) -> dict:
    variants = []
    for variant_id, variant in definition.variants.items():
        fields = [item for field in (variant.get("fields") or []) if (item := _public_field(field)) is not None]
        variants.append({
            "id": str(variant_id),
            "label": str(variant.get("label") or _display_component_label(variant_id)),
            "availability": str(variant.get("availability") or "supported"),
            "unavailable_reason": str(variant.get("unavailable_reason") or ""),
            "fields": fields,
        })
    links = {}
    for key in ("documentation", "website", "repo", "support", "docs"):
        value = (definition.data.get("links") or {}).get(key)
        if value:
            links[key] = str(value)
    return {
        "id": definition.id,
        "name": definition.name,
        "description": str(definition.data.get("description") or ""),
        "category": str(definition.data.get("category") or "other"),
        "tags": _safe_string_list(definition.data.get("tags")),
        "logo": str(definition.data.get("logo") or ""),
        "software_version": definition.software_version,
        "definition_version": definition.definition_version,
        "featured": bool(definition.data.get("featured", False)),
        "features": _safe_string_list(definition.data.get("features")),
        "requirements": _safe_string_list(definition.data.get("requirements")),
        "outputs": _safe_string_list(definition.data.get("outputs")),
        "managed_components": _safe_component_list(definition),
        "links": links,
        "variants": variants,
    }


def public_catalog_definitions() -> list[CatalogDefinition]:
    return [definition for definition in ApplicationCatalog.definitions() if is_public_definition(definition)]


def public_resolution_payload(definition: CatalogDefinition, resolved: dict, resource_summary: dict) -> dict:
    """Project a resolved Ready App into a frontend-safe review payload."""
    variant = definition.variants.get(str(resolved.get("variant_id"))) or {}
    editable_ids = {
        str(field.get("id"))
        for field in (variant.get("fields") or [])
        if field.get("user_editable", True) is not False
    }
    normalized_config = {
        str(key): value
        for key, value in (resolved.get("config") or {}).items()
        if str(key) in editable_ids and key != "slug"
    }

    public_endpoints = []
    domain = str((resolved.get("config") or {}).get("domain") or "").strip()
    scheme = "https" if bool((resolved.get("config") or {}).get("https", True)) else "http"
    for raw_service in resolved.get("services") or []:
        if not raw_service.get("public"):
            continue
        public_endpoints.append({
            "name": _display_component_label(raw_service.get("key")),
            "url": f"{scheme}://{domain}" if domain else "",
        })

    generated_fields = [
        str(field.get("id"))
        for field in (variant.get("fields") or [])
        if field.get("generate") and (
            field.get("type") != "secret"
            and field.get("user_editable", True) is not False
        )
    ]

    return {
        "valid": True,
        "application": {
            "id": definition.id,
            "name": definition.name,
            "software_version": definition.software_version,
            "definition_version": definition.definition_version,
            "variant": str(resolved.get("variant_id") or ""),
        },
        "config": normalized_config,
        "generated_fields": generated_fields,
        "managed_components": public_catalog_definition(definition)["managed_components"],
        "resource_summary": resource_summary,
        "public_endpoints": public_endpoints,
        "outputs": _safe_string_list(definition.data.get("outputs")),
        "warnings": [],
    }


class ApplicationInstanceSerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()
    application_url = serializers.SerializerMethodField()
    resource_summary = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationInstance
        fields = (
            "id", "name", "catalog_id", "definition_version", "software_version", "variant_id",
            "status", "stage", "cancel_requested", "config", "error_code", "error_message", "created_at",
            "updated_at", "deployed_at", "services", "application_url", "resource_summary",
        )

    def get_config(self, obj):
        out = dict(obj.config or {})
        secret_keys = set()
        for binding in obj.services.select_related("service").all():
            secret_keys.update(binding.service.secrets.filter(enabled=True).values_list("key", flat=True))
        out["secrets_configured"] = sorted(secret_keys)
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

    def get_application_url(self, obj):
        for binding in obj.services.select_related("service").all():
            endpoint = binding.service.endpoints.filter(
                enabled=True, exposure="public",
            ).order_by("id").first()
            if endpoint is not None:
                hostname = str(endpoint.hostname or "").strip()
                if hostname:
                    return f"{'https' if endpoint.tls else 'http'}://{hostname}"
        return ""

    def get_resource_summary(self, obj):
        total_storage = 0
        services = []
        for binding in obj.services.select_related("service", "service__plan").all():
            service = binding.service
            storage = sum(int(v.size_mb or 0) for v in service.volumes.all())
            total_storage += storage
            services.append({
                "name": _display_component_label(binding.service_key),
                "role": "database" if str(service.plan.plan_type) == "DB" else "application",
                "cpu_vcpu": service.plan.max_cpu,
                "ram_mb": service.plan.max_ram,
                "storage_mb": storage,
                "storage_limit_mb": int(service.plan.max_storage * 1024),
            })
        return {
            "service_count": len(services),
            "volume_count": sum(1 for binding in obj.services.select_related("service").all() for _ in binding.service.volumes.all()),
            "storage_mb": total_storage,
            "services": services,
        }


def catalog_listing():
    return [public_catalog_definition(definition) for definition in public_catalog_definitions()]
