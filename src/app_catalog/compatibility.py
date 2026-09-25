from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import re
import hashlib

from .compose_catalog import load_compose_yaml
import yaml

from .catalog import CatalogValidationError, CatalogDefinition, resolve_variant, validate_definition
from .compose_catalog import _infer_variable_fields, validate_compose_security, compose_to_resolved
from .plan import ApplicationPlanError, plan_from_resolved


@dataclass
class TemplateAnalysis:
    template_id: str
    path: str
    name: str | None = None
    classification: str = "INVALID"
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    documentation_url: str | None = None
    parser_result: str = ""
    plan_result: str = ""
    service_count: int = 0
    services: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    public_services: list[str] = field(default_factory=list)
    persistent_volumes: int = 0
    healthchecks: int = 0
    build_methods: dict[str, int] = field(default_factory=dict)
    generated_variables: list[str] = field(default_factory=list)
    generated_secrets: list[str] = field(default_factory=list)
    features: dict[str, int] = field(default_factory=dict)
    unsupported_features: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sha256: str | None = None
    networking_class: str = "UNSUPPORTED"
    selection_eligible: bool = False


FEATURE_KEYS = {
    "services": lambda doc: 1 if isinstance(doc.get("services"), dict) else 0,
    "depends_on": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("depends_on")),
    "healthcheck": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("healthcheck")),
    "build": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("build")),
    "image": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("image")),
    "command": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("command")),
    "entrypoint": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("entrypoint")),
    "environment": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("environment")),
    "env_file": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("env_file")),
    "volumes": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("volumes")),
    "named_volumes": lambda doc: len(doc.get("volumes") or {}),
    "bind_mounts": lambda doc: sum(_count_mount_kind(svc.get("volumes") or [], "bind") for svc in (doc.get("services") or {}).values() if isinstance(svc, dict)),
    "networks": lambda doc: len(doc.get("networks") or {}),
    "service_networks": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("networks")),
    "ports": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("ports")),
    "expose": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("expose")),
    "user": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("user")),
    "restart": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("restart")),
    "init": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("init")),
    "profiles": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("profiles")),
    "secrets": lambda doc: 1 if doc.get("secrets") else sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("secrets")),
    "configs": lambda doc: 1 if doc.get("configs") else sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("configs")),
    "privileged": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("privileged")),
    "capabilities": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and (svc.get("cap_add") or svc.get("cap_drop"))),
    "devices": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("devices")),
    "host_network": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("network_mode") == "host"),
    "host_pid_ipc": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and (svc.get("pid") or svc.get("ipc"))),
    "security_opt": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("security_opt")),
    "sysctls": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("sysctls")),
    "ulimits": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("ulimits")),
    "tmpfs": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("tmpfs")),
    "extra_hosts": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("extra_hosts")),
    "dns": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and (svc.get("dns") or svc.get("dns_search"))),
    "platform": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and svc.get("platform")),
    "docker_socket": lambda doc: sum(1 for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) for v in (svc.get("volumes") or []) if "/var/run/docker.sock" in str(v)),
    "coolify_service_urls": lambda doc: _count_text_feature(doc, r"SERVICE_(?:URL|FQDN)_"),
    "coolify_generated_secrets": lambda doc: _count_text_feature(doc, r"SERVICE_(?:PASSWORD|BASE64|REALBASE64)_"),
    "interpolation": lambda doc: _count_text_feature(doc, r"(?<!\$)\$\{?[A-Za-z_][A-Za-z0-9_]*"),
}


def _count_mount_kind(volumes: list[Any], kind: str) -> int:
    count = 0
    for volume in volumes:
        if isinstance(volume, dict) and str(volume.get("type") or "volume") == kind:
            count += 1
        elif isinstance(volume, str) and ":" in volume:
            source = volume.split(":", 1)[0]
            if kind == "bind" and (source.startswith("/") or source.startswith(".") or source.startswith("~")):
                count += 1
    return count


def _count_text_feature(document: dict[str, Any], pattern: str) -> int:
    rx = re.compile(pattern)
    count = 0

    def walk(value: Any) -> None:
        nonlocal count
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            count += len(rx.findall(value))

    walk(document.get("services") or {})
    return count


def _extract_service_roles(document: dict[str, Any], public: set[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for key, raw in (document.get("services") or {}).items():
        if not isinstance(raw, dict):
            continue
        low = str(key).lower()
        explicit = str((raw.get("x-passdeployer") or {}).get("role") or "")
        if explicit:
            roles[str(key)] = explicit
        elif str(key) in public:
            roles[str(key)] = "app"
        elif any(x in low for x in ("postgres", "mysql", "mariadb", "mongo", "database", "db")):
            roles[str(key)] = "database"
        elif any(x in low for x in ("redis", "valkey", "memcached")):
            roles[str(key)] = "cache"
        elif "worker" in low:
            roles[str(key)] = "worker"
        elif any(x in low for x in ("scheduler", "cron")):
            roles[str(key)] = "scheduler"
        elif any(x in low for x in ("gateway", "proxy", "traefik", "nginx", "caddy")):
            roles[str(key)] = "gateway"
        else:
            roles[str(key)] = "internal"
    return roles


def _networking_class(document: dict[str, Any], public_services: set[str], unsupported: list[str]) -> str:
    services = document.get("services") or {}
    has_udp = False
    has_published = False
    has_advanced = False
    for raw in services.values():
        if not isinstance(raw, dict):
            continue
        if any(raw.get(k) for k in ("privileged", "devices", "cap_add", "cap_drop", "security_opt", "sysctls", "pid", "ipc")):
            has_advanced = True
        if raw.get("network_mode"):
            has_advanced = True
        for port in raw.get("ports") or []:
            text = str(port).lower()
            if "/udp" in text:
                has_udp = True
            if ":" in text:
                host = text.split(":", 1)[0]
                if host.isdigit():
                    has_published = True
    custom_networks = {str(k) for k in (document.get("networks") or {}).keys() if str(k) != "default"}
    if custom_networks:
        has_advanced = True
    if any(feature in unsupported for feature in ("docker_socket",)):
        has_advanced = True
    if has_udp or has_advanced:
        return "ADVANCED_NETWORKING"
    if has_published:
        return "WEB_WITH_OPTIONAL_DIRECT_PORTS" if public_services else "WEB_WITH_DIRECT_PORTS"
    if public_services:
        return "STANDARD_WEB"
    return "STANDARD_INTERNAL_SERVICE"


def analyze_document(path: Path) -> TemplateAnalysis:
    analysis = TemplateAnalysis(template_id=path.stem, path=str(path))
    try:
        text = path.read_text("utf-8")
        analysis.sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = load_compose_yaml(text) or {}
        if not isinstance(document, dict):
            raise CatalogValidationError("top-level YAML document must be a mapping")
        if not isinstance(document.get("services"), dict) or not document.get("services"):
            raise CatalogValidationError("missing non-empty services mapping")
    except Exception as exc:
        analysis.errors.append(str(exc))
        analysis.classification = "INVALID"
        return analysis

    analysis.name = path.stem.replace("-", " ").title()
    services = document["services"]
    analysis.services = [str(k) for k in services]
    analysis.service_count = len(services)
    analysis.dependencies = {
        str(k): [str(dep) for dep in ((v.get("depends_on") or {}).keys() if isinstance((v.get("depends_on") or {}), dict) else (v.get("depends_on") or []))]
        for k, v in services.items() if isinstance(v, dict)
    }
    analysis.persistent_volumes = sum(1 for v in services.values() if isinstance(v, dict) for vol in (v.get("volumes") or []) if _is_persistent_volume(vol))
    analysis.healthchecks = sum(1 for v in services.values() if isinstance(v, dict) and v.get("healthcheck"))
    for key, detector in FEATURE_KEYS.items():
        try:
            count = int(detector(document))
        except Exception:
            count = 0
        if count:
            analysis.features[key] = count

    try:
        source_meta = _read_header_meta(text)
        if source_meta.get("ignore"):
            analysis.classification = "IGNORED"
            analysis.parser_result = "SKIPPED"
            analysis.category = source_meta.get("category")
            analysis.tags = list(source_meta.get("tags") or [])
            analysis.documentation_url = source_meta.get("documentation")
            return analysis
        analysis.category = source_meta.get("category")
        analysis.tags = list(source_meta.get("tags") or [])
        analysis.documentation_url = source_meta.get("documentation")
        public = set(str(x) for x in source_meta.get("public_services", []) if x)
        if not public:
            public = _infer_public_services(document)
        if not public and len(document.get("services") or {}) == 1 and source_meta.get("port"):
            public = {str(next(iter(document["services"]))).strip()}
        analysis.public_services = sorted(public)
        roles = _extract_service_roles(document, public)
        analysis.features["role_database"] = sum(1 for r in roles.values() if r == "database")
        analysis.features["role_cache"] = sum(1 for r in roles.values() if r == "cache")
        analysis.features["role_worker"] = sum(1 for r in roles.values() if r == "worker")
        analysis.features["role_scheduler"] = sum(1 for r in roles.values() if r == "scheduler")

        variables = _infer_variable_fields(document)
        analysis.generated_secrets = sorted(fid for fid, field in variables.items() if field.get("secret") or field.get("type") == "secret")
        analysis.generated_variables = sorted(fid for fid in variables if fid not in set(analysis.generated_secrets))

        unsupported = _feature_reasons(document)
        analysis.unsupported_features.extend(unsupported)

        try:
            validate_compose_security(document)
            analysis.parser_result = "OK"
        except Exception as exc:
            analysis.parser_result = "REJECTED"
            analysis.errors.append(str(exc))

        # Generate safe placeholders only for static analysis; never execute or deploy.
        values = _example_values(variables)
        try:
            resolved = compose_to_resolved(
                document=document,
                metadata=source_meta,
                config={k: v for k, v in values.items() if k not in analysis.generated_secrets},
                secrets={k: v for k, v in values.items() if k in analysis.generated_secrets},
                catalog_id=path.stem.lower().replace("_", "-"),
                version="compatibility-check",
            )
            plan = plan_from_resolved(resolved)
            analysis.plan_result = "OK"
            analysis.service_count = len(plan.services)
            analysis.services = [svc.key for svc in plan.services]
            analysis.public_services = sorted(svc.key for svc in plan.services if svc.public)
            if not analysis.public_services and len(plan.services) == 1 and source_meta.get("port"):
                analysis.public_services = [plan.services[0].key]
            analysis.healthchecks = sum(1 for svc in plan.services if svc.healthcheck)
            analysis.persistent_volumes = sum(len(svc.volumes) for svc in plan.services)
            analysis.build_methods = _build_method_counts(plan)
        except Exception as exc:
            analysis.plan_result = "FAILED"
            analysis.errors.append(str(exc))

    except Exception as exc:
        analysis.errors.append(str(exc))

    if analysis.errors and analysis.parser_result != "OK":
        analysis.classification = "UNSUPPORTED" if analysis.unsupported_features else "INVALID"
    elif analysis.plan_result == "FAILED":
        analysis.classification = "UNSUPPORTED"
    elif analysis.warnings or analysis.unsupported_features:
        analysis.classification = "SUPPORTED_WITH_WARNINGS"
    else:
        analysis.classification = "SUPPORTED"
    analysis.networking_class = _networking_class(document, set(analysis.public_services), analysis.unsupported_features)
    # Standard Ready-to-Deploy policy: any Compose `ports:` publication means the
    # application depends on direct host IP:PORT exposure. We do not treat that
    # as equivalent to Traefik-routed HTTP/HTTPS or safely emulate it with a
    # generic allocator. Such applications are unsupported until the platform
    # can guarantee their required external networking semantics.
    has_direct_host_ports = any(
        isinstance(raw, dict) and bool(raw.get("ports"))
        for raw in (document.get("services") or {}).values()
    )
    if has_direct_host_ports:
        if "direct_host_port_publication" not in analysis.unsupported_features:
            analysis.unsupported_features.append("direct_host_port_publication")
        analysis.classification = "UNSUPPORTED"
    analysis.selection_eligible = (
        analysis.classification in {"SUPPORTED", "SUPPORTED_WITH_WARNINGS"}
        and analysis.networking_class in {"STANDARD_WEB", "STANDARD_INTERNAL_SERVICE"}
    )
    return analysis


def _is_persistent_volume(volume: Any) -> bool:
    if isinstance(volume, dict):
        return str(volume.get("type") or "volume") == "volume"
    if isinstance(volume, str):
        if ":" not in volume:
            return False
        source = volume.split(":", 1)[0]
        return not (source.startswith("/") or source.startswith("."))
    return False


def _build_method_counts(plan) -> dict[str, int]:
    result = {"image": 0, "dockerfile": 0, "none": 0}
    for svc in plan.services:
        result[svc.build_kind] = result.get(svc.build_kind, 0) + 1
    return result


def _read_header_meta(text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for line in text.splitlines()[:60]:
        m = re.match(r"^#\s*(category|tags|logo|documentation|slogan|port|ignore):\s*(.+?)\s*$", line, re.I)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "tags":
            meta[key] = [x.strip() for x in value.split(",") if x.strip()]
        elif key == "ignore":
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value
    return meta


def _infer_public_services(document: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    pattern = re.compile(r"\bSERVICE_(?:URL|FQDN)_([A-Za-z0-9_-]+?)(?:_\d+)?(?:\b|\}|$)")
    service_keys = {str(k).lower().replace("-", "").replace("_", "") : str(k) for k in (document.get("services") or {})}
    for raw in (document.get("services") or {}).values():
        env = raw.get("environment") if isinstance(raw, dict) else None
        if isinstance(env, dict):
            values = list(env.values())
        elif isinstance(env, list):
            values = env
        else:
            values = []
        for value in values:
            for match in pattern.finditer(str(value)):
                candidate = match.group(1).lower().replace("-", "").replace("_", "")
                if candidate in service_keys:
                    found.add(service_keys[candidate])
    return found


def _feature_reasons(document: dict[str, Any]) -> list[str]:
    reasons: set[str] = set()
    services = document.get("services") or {}
    top_networks = document.get("networks") or {}
    if top_networks:
        reasons.add("custom_or_external_networks")
    if document.get("secrets"):
        reasons.add("compose_top_level_secrets")
    if document.get("configs"):
        reasons.add("compose_top_level_configs")
    for key, raw in services.items():
        if not isinstance(raw, dict):
            reasons.add(f"invalid_service:{key}")
            continue
        if raw.get("privileged"):
            reasons.add("privileged")
        if raw.get("network_mode"):
            reasons.add("network_mode")
        if raw.get("pid") or raw.get("ipc"):
            reasons.add("host_pid_or_ipc")
        if raw.get("devices"):
            reasons.add("devices")
        if raw.get("cap_add") or raw.get("cap_drop"):
            reasons.add("capabilities")
        if raw.get("security_opt"):
            reasons.add("security_opt")
        if raw.get("sysctls"):
            reasons.add("sysctls")
        if raw.get("ulimits"):
            reasons.add("ulimits")
        if raw.get("tmpfs"):
            reasons.add("tmpfs")
        if raw.get("extra_hosts"):
            reasons.add("extra_hosts")
        if raw.get("dns") or raw.get("dns_search"):
            reasons.add("custom_dns")
        if raw.get("env_file"):
            reasons.add("env_file")
        if raw.get("profiles"):
            reasons.add("profiles")
        if raw.get("container_name"):
            reasons.add("container_name")
        if raw.get("hostname") or raw.get("domainname"):
            reasons.add("hostname_override")
        for vol in raw.get("volumes") or []:
            if _count_mount_kind([vol], "bind"):
                reasons.add("host_bind_mount")
    return sorted(reasons)


def _example_values(variables: dict[str, dict[str, Any]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for fid, field in variables.items():
        if field.get("generate") or field.get("secret") or field.get("type") == "secret":
            values[fid] = "compatibility-secret-value"
        elif "default" in field and field.get("default") not in (None, ""):
            values[fid] = str(field["default"])
        elif field.get("type") == "integer":
            values[fid] = "1"
        elif field.get("type") == "boolean":
            values[fid] = "false"
        elif field.get("type") == "choice":
            options = field.get("options") or ["default"]
            values[fid] = str(options[0])
        elif field.get("type") == "domain":
            values[fid] = "compat.example.invalid"
        else:
            values[fid] = "compat-value"
    return values


def analyze_directory(root: Path) -> list[TemplateAnalysis]:
    results: list[TemplateAnalysis] = []
    for path in sorted(root.rglob("*.y*ml")):
        results.append(analyze_document(path))
    return results


def summarize(results: list[TemplateAnalysis]) -> dict[str, Any]:
    total = len(results)
    counts: dict[str, int] = {key: 0 for key in ("SUPPORTED", "SUPPORTED_WITH_WARNINGS", "UNSUPPORTED", "INVALID", "IGNORED")}
    feature_templates: dict[str, list[str]] = {}
    duplicate_ids: dict[str, list[str]] = {}
    seen_ids: dict[str, str] = {}
    for result in results:
        counts[result.classification] = counts.get(result.classification, 0) + 1
        if result.template_id in seen_ids:
            duplicate_ids.setdefault(result.template_id, [seen_ids[result.template_id]]).append(result.path)
        else:
            seen_ids[result.template_id] = result.path
        for feature in result.unsupported_features:
            feature_templates.setdefault(feature, []).append(result.template_id)

    classification = {
        key: {"count": count, "percentage": round((count / total * 100.0), 2) if total else 0.0}
        for key, count in counts.items()
    }
    incompatibilities = []
    for feature, templates in feature_templates.items():
        incompatibilities.append({
            "feature": feature,
            "count": len(templates),
            "percentage": round((len(templates) / total * 100.0), 2) if total else 0.0,
            "templates": sorted(templates),
        })
    incompatibilities.sort(key=lambda item: (-item["count"], item["feature"]))
    return {
        "total": total,
        "classification": classification,
        "top_incompatibilities": incompatibilities,
        "duplicate_template_ids": duplicate_ids,
    }


def write_report(results: list[TemplateAnalysis], output: Path, *, source_root: Path | None = None) -> None:
    summary = summarize(results)
    payload = {
        "source": {
            "root": str(source_root.resolve()) if source_root else None,
            "template_count": len(results),
        },
        "summary": summary,
        "templates": [asdict(item) for item in results],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
