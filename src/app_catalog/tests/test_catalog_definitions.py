from pathlib import Path

from app_catalog.catalog import (
    ApplicationCatalog,
    CatalogDefinition,
    CatalogValidationError,
    CATALOG_ROOT,
    catalog_cache_key,
    is_public_definition,
    redact_resolved,
    redacted_definition,
    resolve_variant,
)


def test_all_curated_catalog_definitions_validate_and_are_versioned():
    definitions = ApplicationCatalog.definitions()
    # Native TOML definitions may intentionally override imported Compose
    # sources with the same id; the deprecated Synapse MySQL definition is
    # retained on disk but not advertised.
    assert len(definitions) == 41
    ids = {definition.id for definition in definitions}
    assert {"mattermost", "matrix-synapse-with-postgresql", "uptime-kuma", "wordpress-with-mariadb"}.issubset(ids)
    assert "synapse-mysql-mariadb" not in ids
    for definition in definitions:
        assert definition.version
        assert catalog_cache_key(definition)
        assert Path(definition.source).is_file()


def _resolve(catalog_id: str):
    definition = ApplicationCatalog.get(catalog_id)
    fields = {str(f["id"]): f for f in definition.variants["default"].get("fields", [])}
    values = {}
    for fid, field in fields.items():
        if field.get("generate"):
            continue
        if field.get("type") == "domain":
            values[fid] = "app.example.com"
        elif field.get("required") and field.get("type") == "string":
            values[fid] = "example.com"
        elif field.get("required") and field.get("type") == "choice":
            values[fid] = (field.get("options") or ["default"])[0]
        elif field.get("required") and field.get("type") == "integer":
            values[fid] = 1
    return resolve_variant(definition, "default", values)


def test_representative_real_applications_resolve_from_the_generic_catalog():
    for catalog_id in ("mattermost", "matrix-synapse-with-postgresql", "n8n-with-postgres-and-worker", "wordpress-with-mariadb"):
        resolved = _resolve(catalog_id)
        assert resolved["services"]
        assert resolved["metadata"]["name"]


def test_unsupported_legacy_synapse_variant_is_not_exposed():
    try:
        ApplicationCatalog.get("synapse-mysql-mariadb")
    except KeyError:
        return
    raise AssertionError("legacy unsupported Synapse MySQL/MariaDB catalog entry is still active")


def test_preview_redaction_removes_secret_values_from_catalog_definitions():
    definition = ApplicationCatalog.get("mattermost")
    values = {"domain": "chat.example.com"}
    resolved = resolve_variant(definition, "default", values)
    if resolved.get("secrets"):
        preview = redact_resolved(resolved)
        for secret in resolved["secrets"].values():
            if secret:
                assert secret not in str(preview)
    public = redacted_definition(definition)
    for variant in public["variants"].values():
        for field in variant.get("fields", []):
            if field.get("secret") or field.get("type") == "secret":
                assert field.get("default") in (None, "")


def _catalog_example_values(variant):
    values = {}
    for field in variant.get("fields") or []:
        fid = str(field["id"])
        if field.get("generate"):
            continue
        if "default" in field and field.get("default") not in (None, ""):
            values[fid] = field["default"]
        elif field.get("type") == "choice":
            options = field.get("options") or []
            if options:
                values[fid] = options[0]
        elif field.get("type") == "integer":
            values[fid] = 1
        elif field.get("type") == "boolean":
            values[fid] = False
        elif field.get("type") == "domain":
            values[fid] = "app.example.com"
        elif field.get("required"):
            values[fid] = "example-value"
    return values


def test_every_advertised_variant_resolves_to_a_valid_application_plan():
    from app_catalog.plan import plan_from_resolved

    failures = []
    for definition in ApplicationCatalog.definitions():
        for variant_id, variant in definition.variants.items():
            try:
                resolved = resolve_variant(
                    definition,
                    variant_id,
                    _catalog_example_values(variant),
                )
                plan = plan_from_resolved(resolved)
                assert plan.services
                assert len(plan.topological_order()) == len(plan.services)
            except Exception as exc:
                failures.append(f"{definition.id}:{variant_id}: {type(exc).__name__}: {exc}")
    assert not failures, "\n".join(failures)


def test_public_catalog_rejects_unpinned_executable_images():
    source = CATALOG_ROOT / "first_party" / "synthetic-public.yaml"
    base = {
        "id": "synthetic-public",
        "name": "Synthetic Public",
        "version": "1",
        "description": "test",
        "category": "test",
        "visibility": "public",
        "variants": {
            "default": {
                "compose_document": {
                    "services": {
                        "web": {"image": "example/web:latest"},
                    },
                },
                "services": [],
            },
        },
    }

    definition = CatalogDefinition(data=base, source=source)
    assert not is_public_definition(definition)

    base["variants"]["default"]["compose_document"]["services"]["web"]["image"] = "example/web:1.2.3"
    assert is_public_definition(CatalogDefinition(data=base, source=source))

    base["variants"]["default"]["compose_document"]["services"]["web"]["image"] = "example/web"
    assert not is_public_definition(CatalogDefinition(data=base, source=source))

    base["variants"]["default"]["compose_document"]["services"]["web"]["image"] = "example/web:${config.version}"
    assert not is_public_definition(CatalogDefinition(data=base, source=source))
