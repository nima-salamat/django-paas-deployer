from __future__ import annotations

import copy
import hashlib
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from string import Template
import tomllib


CATALOG_ROOT = Path(__file__).resolve().parent / "catalog"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class CatalogValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogDefinition:
    data: dict
    source: Path

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def definition_version(self) -> str:
        return str(self.data.get("definition_version") or self.data.get("template_version") or "1")

    @property
    def software_version(self) -> str:
        return str(self.data.get("software_version") or self.data.get("version") or "unknown")

    @property
    def variants(self) -> dict:
        return dict(self.data.get("variants") or {})

    @property
    def format(self) -> str:
        return str(self.data.get("format") or "toml")


class ApplicationCatalog:
    @classmethod
    def definitions(cls) -> list[CatalogDefinition]:
        result: dict[str, CatalogDefinition] = {}
        for path in sorted(CATALOG_ROOT.glob("*.toml")):
            data = tomllib.loads(path.read_text("utf-8"))
            validate_definition(data, source=str(path))
            result[str(data["id"])] = CatalogDefinition(data=data, source=path)
        # The active first-party catalog is deliberately curated. Experimental/legacy
        # definitions live outside this directory and are not exposed as Ready-to-Deploy.
        from .source_loader import load_yaml_definition, external_definitions
        first_party = CATALOG_ROOT / "first_party"
        if first_party.exists():
            for path in sorted(first_party.glob("*.y*ml")):
                definition = load_yaml_definition(path)
                if definition is None:
                    continue
                validate_definition(definition.data, source=str(path))
                if definition.id in result:
                    raise CatalogValidationError(
                        f"Duplicate catalog id {definition.id!r}: {result[definition.id].source} and {path}"
                    )
                result[definition.id] = definition
        for definition in external_definitions():
            validate_definition(definition.data, source=str(definition.source))
            if definition.id in result:
                raise CatalogValidationError(
                    f"Duplicate catalog id {definition.id!r}: {result[definition.id].source} and {definition.source}"
                )
            result[definition.id] = definition
        return [result[key] for key in sorted(result)]

    @classmethod
    def get(cls, catalog_id: str) -> CatalogDefinition:
        for definition in cls.definitions():
            if definition.id == catalog_id:
                return definition
        raise KeyError(catalog_id)


def validate_definition(data: dict, *, source: str = "catalog") -> None:
    for key in ("id", "name", "version", "description", "category", "variants"):
        if key not in data:
            raise CatalogValidationError(f"{source}: missing {key}")
    if not ID_RE.fullmatch(str(data["id"])):
        raise CatalogValidationError(f"{source}: invalid id")
    variants = data.get("variants") or {}
    if not isinstance(variants, dict) or not variants:
        raise CatalogValidationError(f"{source}: at least one variant is required")
    for variant_id, variant in variants.items():
        if not isinstance(variant, dict):
            raise CatalogValidationError(f"{source}: variant {variant_id} must be a table")
        fields = variant.get("fields") or []
        seen_fields = set()
        for field in fields:
            fid = str(field.get("id") or "")
            if not fid or fid in seen_fields:
                raise CatalogValidationError(f"{source}: duplicate/invalid field {fid!r}")
            seen_fields.add(fid)
            if field.get("type") not in {"string", "integer", "boolean", "choice", "domain", "secret"}:
                raise CatalogValidationError(f"{source}: unsupported field type for {fid}")
            if field.get("type") == "choice" and not field.get("options"):
                raise CatalogValidationError(f"{source}: choice field {fid} requires options")
        services = variant.get("services") or []
        service_keys = set()
        if variant.get("compose_document") is not None:
            raw_services = variant["compose_document"].get("services") or {}
            if not isinstance(raw_services, dict) or not raw_services:
                raise CatalogValidationError(f"{source}: Compose definition must contain services")
            service_keys = {str(key) for key in raw_services}
            for key, svc in raw_services.items():
                if not isinstance(svc, dict):
                    raise CatalogValidationError(f"{source}: Compose service {key!r} must be an object")
                depends = svc.get("depends_on") or {}
                depends = depends.keys() if isinstance(depends, dict) else depends
                for dep in depends:
                    if str(dep) not in service_keys:
                        raise CatalogValidationError(f"{source}: {key} depends on unknown service {dep}")
        else:
            for svc in services:
                key = str(svc.get("key") or "")
                if not key or key in service_keys:
                    raise CatalogValidationError(f"{source}: duplicate/invalid service key {key!r}")
                service_keys.add(key)
                if svc.get("role") not in {"app", "database", "cache", "worker", "scheduler", "proxy", "gateway", "analytics", "storage", "internal"}:
                    raise CatalogValidationError(f"{source}: unsupported role in {key}")
                if not svc.get("platform"):
                    raise CatalogValidationError(f"{source}: missing platform in {key}")
            for svc in services:
                for dep in svc.get("depends_on") or []:
                    if dep not in service_keys:
                        raise CatalogValidationError(f"{source}: {svc['key']} depends on unknown service {dep}")


def _generate(spec: str) -> str:
    kind, _, raw = str(spec).partition(":")
    if kind == "hex":
        return secrets.token_hex(max(1, int(raw or 16) // 2))
    if kind == "password":
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_"
        return "".join(secrets.choice(alphabet) for _ in range(max(16, int(raw or 24))))
    if kind == "uuid":
        import uuid
        return str(uuid.uuid4())
    raise CatalogValidationError(f"Unsupported generator {spec!r}")


def resolve_variant(definition: CatalogDefinition, variant_id: str, values: dict | None = None) -> dict:
    variant = definition.variants.get(variant_id)
    if variant is None:
        raise CatalogValidationError(f"Unknown variant {variant_id!r}")
    if str(variant.get("availability", "supported")) != "supported":
        raise CatalogValidationError(str(variant.get("unavailable_reason") or "This application variant is not supported."))

    supplied = dict(values or {})
    known_fields = {str(field["id"]) for field in (variant.get("fields") or [])}
    unknown = sorted(set(supplied) - known_fields)
    if unknown:
        raise CatalogValidationError(
            "Unknown configuration option(s): " + ", ".join(unknown)
        )
    config: dict = {}
    secrets_map: dict = {}
    for field in variant.get("fields") or []:
        fid = str(field["id"])
        value = supplied.get(fid)
        if value in (None, ""):
            if field.get("generate"):
                value = _generate(str(field["generate"]))
            elif "default" in field:
                value = field["default"]
        if field.get("required") and value in (None, ""):
            raise CatalogValidationError(f"{field.get('label', fid)} is required.")
        if field.get("type") == "choice" and value not in set(field.get("options") or []):
            raise CatalogValidationError(f"Invalid value for {field.get('label', fid)}.")
        pattern = field.get("pattern")
        if value not in (None, "") and pattern and not re.fullmatch(str(pattern), str(value)):
            raise CatalogValidationError(f"Invalid value for {field.get('label', fid)}.")
        if field.get("type") == "integer" and value not in (None, ""):
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise CatalogValidationError(f"{field.get('label', fid)} must be an integer.") from exc
        if field.get("secret") or field.get("type") == "secret":
            secrets_map[fid] = str(value or "")
        else:
            config[fid] = value

    context = {"config": config, "secret": secrets_map}
    if variant.get("compose_document") is not None:
        from .compose_catalog import compose_to_resolved
        resolved = compose_to_resolved(
            document=dict(variant.get("compose_document") or {}),
            metadata=dict(variant.get("compose_metadata") or {}),
            config=config,
            secrets=secrets_map,
            catalog_id=definition.id,
            version=definition.software_version,
            variant=variant_id,
        )
        resolved["metadata"].update({
            "name": definition.name,
            "description": definition.data.get("description", ""),
            "category": definition.data.get("category", "other"),
            "tags": definition.data.get("tags", []),
            "links": definition.data.get("links", {}),
        })
        return resolved
    return {
        "catalog_id": definition.id,
        "definition_version": definition.definition_version,
        "software_version": definition.software_version,
        "variant_id": variant_id,
        "config": config,
        "secrets": secrets_map,
        "services": _render_services(variant.get("services") or [], context),
        "metadata": {
            "name": definition.name,
            "description": definition.data.get("description", ""),
            "category": definition.data.get("category", "other"),
            "links": definition.data.get("links", {}),
        },
    }


def _render_services(services: list[dict], context: dict) -> list[dict]:
    service_names = {svc["key"]: svc.get("name_template") for svc in services}
    rendered = []
    for svc in services:
        row = dict(svc)
        row["name_template"] = _render_template(row.get("name_template", svc["key"]), context)
        row["environment"] = {str(k): _render_template(str(v), context) for k, v in (svc.get("environment") or {}).items()}
        row["dockerfile"] = _render_template(str(svc.get("dockerfile", "")), context)
        row["volumes"] = [
            {
                str(key): _render_template(str(value), context) if isinstance(value, str) else value
                for key, value in dict(volume).items()
            }
            for volume in (svc.get("volumes") or [])
        ]
        rendered.append(row)
    return rendered


def _render_template(value: str, context: dict) -> str:
    if not isinstance(value, str) or "${" not in value:
        return value
    out = value
    for root in ("config", "secret"):
        for key, v in context[root].items():
            out = out.replace("${%s.%s}" % (root, key), str(v))
    return out



def redact_resolved(resolved: dict) -> dict:
    """Return a preview-safe resolved definition without secret values.

    Catalog resolution intentionally renders secrets into the private deployment
    plan, but API previews must never echo those values back through service
    environment variables, files, or other nested structures.
    """
    payload = copy.deepcopy(resolved)
    secret_values = {str(v) for v in (payload.get("secrets") or {}).values() if v not in (None, "")}

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

    payload["secrets"] = {key: "[REDACTED]" for key in (payload.get("secrets") or {})}
    payload["services"] = redact(payload.get("services") or [])
    return payload

def redacted_definition(definition: CatalogDefinition) -> dict:
    payload = copy.deepcopy(definition.data)
    for variant in (payload.get("variants") or {}).values():
        for field in variant.get("fields") or []:
            if field.get("secret") or field.get("type") == "secret":
                field["default"] = None
    return payload


def catalog_cache_key(definition: CatalogDefinition) -> str:
    return hashlib.sha256(definition.source.read_bytes()).hexdigest()
