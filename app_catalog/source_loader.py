from __future__ import annotations

import os
import re
from pathlib import Path
import tomllib
from .compose_catalog import load_compose_yaml
import yaml

from .compose_catalog import validate_compose_security, _infer_variable_fields
from .catalog import CatalogDefinition, CatalogValidationError

HEADER_RE = re.compile(r"^#\s*(documentation|slogan|category|tags|logo|port|minversion|ignore):\s*(.+?)\s*$", re.I)


def _source_dirs() -> list[Path]:
    raw = os.getenv("APP_CATALOG_SOURCE_DIRS", "")
    return [Path(item).expanduser().resolve() for item in raw.split(os.pathsep) if item.strip()]


def _header_metadata(text: str) -> dict:
    meta = {}
    for line in text.splitlines()[:40]:
        m = HEADER_RE.match(line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "tags":
            meta[key] = [part.strip() for part in value.split(",") if part.strip()]
        elif key == "port":
            try:
                meta[key] = int(value)
            except ValueError:
                pass
        elif key == "ignore":
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value
    return meta


def _meta_for(path: Path, document: dict) -> dict:
    candidates = [path.with_suffix(".catalog.toml"), path.with_name(path.stem + ".meta.toml")]
    for candidate in candidates:
        if candidate.is_file():
            return tomllib.loads(candidate.read_text("utf-8"))
    return _header_metadata(path.read_text("utf-8"))


def load_yaml_definition(path: Path) -> CatalogDefinition | None:
    text = path.read_text("utf-8")
    document = load_compose_yaml(text) or {}
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise CatalogValidationError(f"{path}: Compose file must contain services")
    try:
        validate_compose_security(document)
    except Exception as exc:
        raise CatalogValidationError(f"{path}: {exc}") from exc
    xpd = dict(document.get("x-passdeployer") or {})
    header = _header_metadata(text)
    meta = {**header, **xpd}
    if bool(meta.get("ignore")):
        return None
    app_id = str(meta.get("id") or path.stem).strip().lower().replace("_", "-")
    name = str(meta.get("name") or meta.get("title") or path.stem.replace("-", " ").title())
    version = str(meta.get("version") or "imported")
    inferred = _infer_variable_fields(document)
    variant = {
        "fields": list(meta.get("fields") or list(inferred.values())),
        "services": [],
        "compose_document": document,
        "compose_metadata": meta,
    }
    for key, raw in document["services"].items():
        if not isinstance(raw, dict):
            continue
        variant["services"].append({"key": key, **raw})
    data = {
        "id": app_id,
        "name": name,
        "version": version,
        "software_version": version,
        "definition_version": str(meta.get("definition_version") or meta.get("template_version") or "1"),
        "description": str(meta.get("slogan") or meta.get("description") or ""),
        "category": str(meta.get("category") or "other"),
        "tags": list(meta.get("tags") or []),
        "links": {k: meta[k] for k in ("documentation", "website", "repo", "support", "docs") if meta.get(k)},
        "source_url": meta.get("source_url") or meta.get("repository") or "",
        "format": "compose",
        "variants": {"default": variant},
    }
    if not meta.get("public_services") and not meta.get("public_service"):
        import re
        candidates = set()
        for raw in document["services"].values():
            env = raw.get("environment") or {}
            values = list(env.values()) if isinstance(env, dict) else list(env)
            for value in values:
                text = str(value)
                for match in re.finditer(r"SERVICE_(?:URL|FQDN)_([A-Za-z0-9_-]+?)(?:_\d+)?(?:\}|$|[^A-Za-z0-9_-])", text):
                    candidates.add(match.group(1).lower().replace("-", "_"))
        if candidates:
            data["variants"]["default"]["compose_metadata"]["public_services"] = sorted(candidates)
        else:
            ports = [
                key for key, raw in document["services"].items()
                if any(True for _ in (raw.get("ports") or []))
            ]
            if len(ports) == 1:
                data["variants"]["default"]["compose_metadata"]["public_services"] = ports
    return CatalogDefinition(data=data, source=path)


def external_definitions() -> list[CatalogDefinition]:
    result = []
    for root in _source_dirs():
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.y*ml")):
            try:
                definition = load_yaml_definition(path)
                if definition is not None:
                    result.append(definition)
            except Exception as exc:
                raise CatalogValidationError(f"Unable to ingest {path}: {exc}") from exc
    return result
