from __future__ import annotations

from rest_framework import serializers
from .catalog import ApplicationCatalog, CatalogDefinition, is_public_definition, public_catalog_definitions
from .models import ApplicationInstance


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


def _public_variant_services(variant: dict) -> list[dict]:
    """Expose safe child identity and resource-plan requirements, never secrets."""
    raw_services = variant.get("services") or []
    compose_document = variant.get("compose_document") or {}
    if not raw_services and isinstance(compose_document, dict):
        compose_services = compose_document.get("services") or {}
        if isinstance(compose_services, dict):
            raw_services = [
                {"key": str(key), **(value if isinstance(value, dict) else {})}
                for key, value in compose_services.items()
            ]

    rows = []
    for item in raw_services:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("service_key") or "").strip()
        if not key:
            continue

        # Built-in Compose catalog definitions use x-passdeployer extensions;
        # imported Compose documents can use explicit top-level fields. Mirror
        # compose_to_resolved() here so the wizard displays the same platform
        # and PlanType that installation will enforce.
        pd_meta = item.get("x-passdeployer") or {}
        role = str(pd_meta.get("role") or item.get("role") or "").strip().lower()
        image_hint = str(item.get("image") or item.get("image_template") or "").lower()
        database_platform = next(
            (
                candidate
                for marker, candidate in (
                    ("postgres", "postgresql"),
                    ("mariadb", "mariadb"),
                    ("mysql", "mysql"),
                    ("mongo", "mongodb"),
                    ("oracle", "oracle"),
                )
                if marker in image_hint or marker in key.lower()
            ),
            None,
        )
        if not role:
            low = key.lower()
            if database_platform or any(token in low for token in ("database", "db")):
                role = "database"
            elif "redis" in low or "valkey" in low:
                role = "cache"
            elif "worker" in low:
                role = "worker"
            elif "scheduler" in low or "cron" in low:
                role = "scheduler"
            elif bool(pd_meta.get("public")) or bool(item.get("public")):
                role = "app"
            else:
                role = "internal"

        explicit_platform = (
            pd_meta.get("platform")
            or item.get("platform")
        )
        explicit_plan_type = (
            pd_meta.get("plan_type")
            or item.get("plan_type")
        )
        if role == "database":
            platform = str(explicit_platform or database_platform or "").lower()
            plan_type = str(explicit_plan_type or "DB").upper()
        else:
            platform = str(explicit_platform or "docker").lower()
            plan_type = str(explicit_plan_type or "APP").upper()

        try:
            replicas = max(1, int(item.get("replicas", pd_meta.get("replicas", 1)) or 1))
        except (TypeError, ValueError):
            replicas = 1
        rows.append({
            "key": key,
            "label": _display_component_label(item.get("label") or pd_meta.get("label") or key),
            "role": role,
            "platform": platform,
            "plan_type": plan_type,
            "required": bool(item.get("required", pd_meta.get("required", True))),
            "replicas": replicas,
            "depends_on": _safe_string_list(item.get("depends_on")),
        })
    return rows


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


def _publication_featured_overrides() -> dict[str, bool | None]:
    """Load featured overrides once for catalog-list serialization."""
    try:
        from .models import CatalogPublication
        return {
            str(row["catalog_id"]): row["featured_override"]
            for row in CatalogPublication.objects.values("catalog_id", "featured_override")
        }
    except Exception:
        return {}


def catalog_featured(
    definition: CatalogDefinition,
    *,
    featured_overrides: dict[str, bool | None] | None = None,
) -> bool:
    """Return the effective operator/editorial featured flag."""
    featured = bool(definition.data.get("featured", False))
    if featured_overrides is not None and definition.id in featured_overrides:
        override = featured_overrides[definition.id]
        return featured if override is None else bool(override)
    try:
        from .models import CatalogPublication
        override = (
            CatalogPublication.objects
            .filter(catalog_id=definition.id)
            .values_list("featured_override", flat=True)
            .first()
        )
    except Exception:
        override = None
    return featured if override is None else bool(override)

def public_catalog_definition(
    definition: CatalogDefinition,
    *,
    featured_overrides: dict[str, bool | None] | None = None,
) -> dict:
    variants = []
    for variant_id, variant in definition.variants.items():
        fields = [item for field in (variant.get("fields") or []) if (item := _public_field(field)) is not None]
        variants.append({
            "id": str(variant_id),
            "label": str(variant.get("label") or _display_component_label(variant_id)),
            "availability": str(variant.get("availability") or "supported"),
            "unavailable_reason": str(variant.get("unavailable_reason") or ""),
            "fields": fields,
            "services": _public_variant_services(variant),
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
        "featured": catalog_featured(definition, featured_overrides=featured_overrides),
        "features": _safe_string_list(definition.data.get("features")),
        "requirements": _safe_string_list(definition.data.get("requirements")),
        "outputs": _safe_string_list(definition.data.get("outputs")),
        "managed_components": _safe_component_list(definition),
        "links": links,
        "variants": variants,
    }


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
            "software_version": str(
                (resolved.get("config") or {}).get("software_version")
                or definition.software_version
            ),
            "definition_version": definition.definition_version,
            "variant": str(resolved.get("variant_id") or ""),
        },
        "config": normalized_config,
        "generated_fields": generated_fields,
        "managed_components": public_catalog_definition(definition)["managed_components"],
        "resource_summary": resource_summary,
        "outputs": _safe_string_list(definition.data.get("outputs")),
        "warnings": [],
    }


class ApplicationInstanceSerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()
    application_url = serializers.SerializerMethodField()
    application_host = serializers.SerializerMethodField()
    resource_summary = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationInstance
        fields = (
            "id", "name", "catalog_id", "definition_version", "software_version", "variant_id",
            "status", "stage", "cancel_requested", "config", "error_code", "error_message", "created_at",
            "updated_at", "deployed_at", "services", "application_url", "application_host", "resource_summary",
        )

    def get_config(self, obj):
        out = dict(obj.config or {})
        secret_keys = set()
        for binding in obj.services.select_related("service").all():
            secret_keys.update(binding.service.secrets.filter(enabled=True).values_list("key", flat=True))
        out["secrets_configured"] = sorted(secret_keys)
        return out

    @staticmethod
    def _canonical_service_host(service):
        try:
            from services.serializers import _service_host
            return str(_service_host(service) or "").strip()
        except Exception:
            try:
                return str(service.get_docker_service_name() or "").strip()
            except Exception:
                return ""

    def get_services(self, obj):
        rows = []
        for binding in obj.services.select_related("service", "deploy", "service__plan").all():
            deploy = binding.deploy
            service = binding.service
            service_host = self._canonical_service_host(service)
            endpoints = []
            for endpoint in service.endpoints.filter(enabled=True, exposure="public").order_by("id"):
                # Platform-managed Ready App hosts must always use the canonical
                # Service-derived hostname. Explicit custom hostnames remain
                # available for non-catalog services.
                endpoint_host = service_host or str(endpoint.hostname or "").strip()
                url = ""
                if endpoint_host:
                    scheme = "https" if endpoint.tls else "http"
                    url = f"{scheme}://{endpoint_host}"
                    if endpoint.path:
                        url = f"{url.rstrip('/')}/{str(endpoint.path).lstrip('/')}"
                endpoints.append({
                    "name": endpoint.name,
                    "hostname": endpoint_host,
                    "url": url,
                    "target_port": endpoint.target_port,
                    "protocol": endpoint.protocol,
                    "tls": bool(endpoint.tls),
                    "path": endpoint.path,
                })
            rows.append({
                "key": binding.service_key,
                "service_id": str(binding.service_id),
                "service_name": service.name,
                "service_host": service_host,
                "deploy_id": str(deploy.pk),
                "status": service.status,
                "deploy_status": deploy.status,
                "stage": deploy.stage,
                "status_message": deploy.status_message,
                "error_message": deploy.error_message if deploy.status == "failed" else "",
                "plan": {
                    "id": str(service.plan_id),
                    "name": str(getattr(service.plan, "name", "") or ""),
                    "platform": str(getattr(service.plan, "platform", "") or ""),
                    "plan_type": str(getattr(service.plan, "plan_type", "") or ""),
                },
                "resource_limits": {
                    "cpu_vcpu": getattr(service.plan, "max_cpu", None),
                    "ram_mb": getattr(service.plan, "max_ram", None),
                    "storage_mb": sum(int(v.size_mb or 0) for v in service.volumes.all()),
                },
                "public_endpoints": endpoints,
            })
        return rows

    def _public_service_host(self, obj):
        for binding in obj.services.select_related("service").all():
            service = binding.service
            endpoint = service.endpoints.filter(
                enabled=True, exposure="public",
            ).order_by("id").first()
            if endpoint is None:
                continue
            host = self._canonical_service_host(service)
            if not host:
                host = str(endpoint.hostname or "").strip()
            if host:
                return host
        return ""

    def get_application_host(self, obj):
        return self._public_service_host(obj)

    def get_application_url(self, obj):
        # A Ready App public hostname is derived from the Service identity, not
        # a mutable/stale endpoint snapshot. Do not expose a URL until the
        # application is actually running.
        if obj.status != "running":
            return ""
        host = self._public_service_host(obj)
        if not host:
            return ""
        endpoint = None
        for binding in obj.services.select_related("service").all():
            endpoint = binding.service.endpoints.filter(
                enabled=True, exposure="public",
            ).order_by("id").first()
            if endpoint is not None:
                break
        scheme = "https" if endpoint is None or endpoint.tls else "http"
        path = str(endpoint.path or "").strip() if endpoint is not None else ""
        url = f"{scheme}://{host}"
        return f"{url.rstrip('/')}/{path.lstrip('/')}" if path else url

    def get_resource_summary(self, obj):
        total_storage = 0
        services = []
        for binding in obj.services.select_related("service", "service__plan").all():
            service = binding.service
            storage = sum(int(v.size_mb or 0) for v in service.volumes.all())
            total_storage += storage
            services.append({
                "key": str(binding.service_key),
                "name": _display_component_label(binding.service_key),
                "role": "database" if str(service.plan.plan_type) == "DB" else "application",
                "plan_id": str(service.plan_id),
                "plan": {
                    "name": str(service.plan.name),
                    "platform": str(service.plan.platform),
                    "plan_type": str(service.plan.plan_type),
                },
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
    featured_overrides = _publication_featured_overrides()
    return [
        public_catalog_definition(
            definition,
            featured_overrides=featured_overrides,
        )
        for definition in public_catalog_definitions()
    ]
