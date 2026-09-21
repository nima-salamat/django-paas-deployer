from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import yaml

from .plan import ApplicationPlanError


class ComposeSafeLoader(yaml.SafeLoader):
    """Compose-oriented YAML loader without YAML 1.1 sexagesimal integers."""


# PyYAML's default YAML 1.1 integer resolver interprets unquoted `22222:22`
# as a base-60 integer. Docker Compose uses this syntax for port mappings,
# so remove only that legacy resolver branch while retaining normal integers.
for _ch, _resolvers in list(ComposeSafeLoader.yaml_implicit_resolvers.items()):
    adjusted = []
    for _tag, _rx in _resolvers:
        if _tag == "tag:yaml.org,2002:int":
            _pattern = getattr(_rx, "pattern", "")
            if ":" in _pattern and "[0-9_]*(?::[0-5]?[0-9])+" in _pattern:
                _pattern = r"^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+)$"
                _rx = re.compile(_pattern)
        adjusted.append((_tag, _rx))
    ComposeSafeLoader.yaml_implicit_resolvers[_ch] = adjusted


def load_compose_yaml(text: str) -> dict[str, Any]:
    document = yaml.load(text, Loader=ComposeSafeLoader) or {}
    if not isinstance(document, dict):
        raise ApplicationPlanError("Compose definition must be a mapping.")
    return document


_VAR_RE = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([-?+])(.*?))?\}|(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*)")

UNSAFE_SERVICE_KEYS = {
    "deploy", "network_mode", "privileged", "pid", "ipc", "uts", "userns_mode",
    "devices", "cap_add", "cap_drop", "security_opt", "sysctls", "ulimits", "runtime",
    "secrets", "configs", "credential_spec", "tmpfs", "init",
    # These Docker/Compose semantics are not represented by ApplicationPlan
    # yet; rejecting them is safer than silently changing their meaning.
    "container_name", "hostname", "domainname", "dns", "dns_search",
    "extra_hosts", "profiles", "extends",
}


def _normalize_environment(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, list):
        return {}
    result: dict[str, Any] = {}
    for item in value:
        text = str(item)
        if "=" in text:
            key, env_value = text.split("=", 1)
            result[str(key)] = env_value
            continue
        key = text.strip()
        if re.fullmatch(r"SERVICE_(URL|FQDN)_[A-Za-z0-9_-]+", key):
            result[key] = "${config.domain}"
        elif re.fullmatch(r"SERVICE_USER_[A-Za-z0-9_-]+", key):
            result[key] = f"${{config.{key.lower()}}}"
        elif re.fullmatch(r"SERVICE_PASSWORD_[A-Za-z0-9_-]+", key):
            result[key] = f"${{secret.{key.lower()}}}"
        else:
            raise ApplicationPlanError(
                f"Compose environment entry {key!r} relies on inherited host environment; "
                "declare a value explicitly or use a supported catalog variable."
            )
    return result


def _meta_fields(meta: dict[str, Any], variables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    fields = []
    explicit = meta.get("fields") or []
    seen = set()
    for field in explicit:
        item = dict(field)
        fid = str(item.get("id") or "")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        fields.append(item)
    for fid, item in variables.items():
        if fid in seen:
            continue
        fields.append(dict(item))
    return fields


def _infer_variable_fields(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def add_field(name: str, *, explicit_kind: str | None = None, default: str | None = None, required: bool = False) -> None:
        field_name = name.lower()
        if explicit_kind == "secret":
            found.setdefault(field_name, {
                "id": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "secret",
                "secret": True,
                "generate": "password:32",
            })
            return
        field_type = "domain" if field_name in {"domain", "hostname", "url"} else "string"
        found.setdefault(field_name, {
            "id": field_name,
            "label": field_name.replace("_", " ").title(),
            "type": field_type,
            "default": default or "",
            **({"required": True} if required else {}),
        })

    def walk(value: Any):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for bare in re.finditer(r"\bSERVICE_(URL|FQDN|USER|PASSWORD)_([A-Za-z0-9_-]+)", value):
                kind, suffix = bare.group(1), bare.group(2)
                if kind in {"URL", "FQDN"}:
                    add_field("domain", explicit_kind="config", required=True)
                elif kind == "PASSWORD":
                    add_field(f"service_password_{suffix.lower()}", explicit_kind="secret")
                else:
                    add_field(f"service_user_{suffix.lower()}", default="app")
            for explicit in re.finditer(r"\$\{(config|secret)\.([A-Za-z_][A-Za-z0-9_]*)\}", value):
                add_field(explicit.group(2), explicit_kind=explicit.group(1))
            for match in _VAR_RE.finditer(value):
                name = match.group(1) or match.group(4)
                op = match.group(2)
                default = match.group(3)
                if not name:
                    continue
                # Coolify-specific generated values should become generated
                # catalog secrets/user/URL inputs rather than raw fields.
                if name.startswith("SERVICE_PASSWORD_") or any(x in name.upper() for x in ("PASSWORD", "SECRET", "TOKEN")):
                    add_field(name, explicit_kind="secret")
                elif name.startswith("SERVICE_USER_"):
                    field_name = name.lower()
                    found.setdefault(field_name, {"id": field_name, "label": name.replace("_", " ").title(), "type": "string", "default": "app"})
                elif name.startswith("SERVICE_URL_") or name.startswith("SERVICE_FQDN_"):
                    add_field("domain", explicit_kind="config", required=True)
                else:
                    add_field(name, default=default, required=(op == "?"))
    walk(document)
    return found


def _transform(value: Any, resolved: dict[str, Any], aliases: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {str(k): _transform(v, resolved, aliases) for k, v in value.items()}
    if isinstance(value, list):
        return [_transform(v, resolved, aliases) for v in value]
    if not isinstance(value, str):
        return value

    # PassDeployer catalog definitions may use explicit references in addition
    # to native Compose variables. These are resolved before/alongside the
    # Coolify-style $NAME / ${NAME:-default} syntax.
    def replace_catalog_ref(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        value = resolved.get(f"{kind}.{name}")
        if value is None:
            raise ApplicationPlanError(f"Required catalog variable {kind}.{name} is not configured.")
        return str(value)

    value = re.sub(r"\$\{(config|secret)\.([A-Za-z_][A-Za-z0-9_]*)\}", replace_catalog_ref, value)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(4)
        op = match.group(2)
        default = match.group(3)
        field_id = aliases.get(name, name.lower())
        if name.startswith("SERVICE_URL_") or name.startswith("SERVICE_FQDN_"):
            field_id = "domain"
        value = resolved.get(field_id)
        if value in (None, ""):
            if op in (":", "-") and default is not None:
                return default
            if op == "?":
                raise ApplicationPlanError(f"Required template variable {name} is not configured.")
            return ""
        return str(value)

    return _VAR_RE.sub(replace, value).replace("$$", "$")


def _service_url_keys(document: dict[str, Any]) -> set[str]:
    """Infer public service keys from Coolify-style SERVICE_URL/FQDN variables."""
    keys: set[str] = set()
    pattern = re.compile(r"(?<!\$)(?:\$\{)?SERVICE_(?:URL|FQDN)_([A-Za-z0-9_-]+?)(?:_\d+)?(?:\})?(?:$|[^A-Za-z0-9_-])")

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for match in pattern.finditer(value):
                keys.add(match.group(1).lower().replace("-", "_"))
    walk(document.get("services") or {})
    return keys


def _duration_seconds(value: Any, default: float) -> float:
    if value in (None, ""):
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)?", text)
    if not m:
        raise ApplicationPlanError(f"Unsupported Compose duration {value!r}.")
    amount = float(m.group(1))
    unit = m.group(2) or "s"
    return amount / 1000 if unit == "ms" else amount if unit == "s" else amount * 60 if unit == "m" else amount * 3600


def validate_compose_security(document: dict[str, Any]) -> None:
    if not isinstance(document.get("services"), dict) or not document.get("services"):
        raise ApplicationPlanError("Compose definition must contain a services mapping.")
    if document.get("secrets") or document.get("configs"):
        raise ApplicationPlanError("Catalog Compose top-level secrets/configs are not supported yet; use catalog secret fields and generated files instead.")
    declared_networks = set((document.get("networks") or {}).keys())
    declared_networks.discard("default")
    if declared_networks:
        raise ApplicationPlanError("Catalog Compose files may not declare custom/external Docker networks; PassDeployer owns the application network.")
    for key, raw in document["services"].items():
        if not isinstance(raw, dict):
            raise ApplicationPlanError(f"Compose service {key!r} must be an object.")
        unsupported = sorted(UNSAFE_SERVICE_KEYS & set(raw))
        if unsupported:
            raise ApplicationPlanError(f"Compose service {key!r} uses unsupported security/execution features: {', '.join(unsupported)}")
        raw_networks = raw.get("networks") or {}
        networks = set(raw_networks) if not isinstance(raw_networks, dict) else set(raw_networks)
        if networks and networks != {"default"}:
            raise ApplicationPlanError(f"Catalog service {key!r} references custom Docker networks, which PassDeployer does not import yet.")
        env_probe = _normalize_environment(raw.get("environment") or {})
        for env_key, env_value in env_probe.items():
            if any(token in str(env_key).upper() for token in ("PASSWORD", "SECRET", "TOKEN", "PRIVATE_KEY")):
                text = str(env_value)
                if text and "$" not in text and text.lower() not in {"changeme", "change-me", "example", "admin"}:
                    raise ApplicationPlanError(f"Catalog service {key!r} contains a hard-coded sensitive environment value for {env_key}.")
        depends_on = raw.get("depends_on") or {}
        if isinstance(depends_on, dict):
            for dep, condition in depends_on.items():
                condition_name = condition.get("condition") if isinstance(condition, dict) else "service_started"
                if condition_name not in {"service_started", "service_healthy"}:
                    raise ApplicationPlanError(f"Compose dependency {key}->{dep} uses unsupported condition {condition_name!r}.")


def compose_to_resolved(*, document: dict[str, Any], metadata: dict[str, Any], config: dict[str, Any], secrets: dict[str, Any], catalog_id: str, version: str, variant: str = "default") -> dict[str, Any]:
    validate_compose_security(document)
    variables = _infer_variable_fields(document)
    merged = dict(config)
    merged.update(secrets)
    render_context = dict(merged)
    render_context.update({f"config.{k}": v for k, v in config.items()})
    render_context.update({f"secret.{k}": v for k, v in secrets.items()})
    aliases = {name: ("domain" if name.startswith(("SERVICE_URL_", "SERVICE_FQDN_")) else name.lower()) for name in variables}
    metadata = dict(metadata or {})
    public_services = set(str(x) for x in (metadata.get("public_services") or []))
    if metadata.get("public_service"):
        public_services.add(str(metadata["public_service"]))
    if not public_services:
        public_services.update(_service_url_keys(document))
    service_keys = {str(k): str(k).lower().replace("-", "").replace("_", "") for k in document["services"]}
    normalized_public = set()
    for public_key in public_services:
        candidate = str(public_key).lower().replace("-", "").replace("_", "")
        for service_key, normalized in service_keys.items():
            if candidate == normalized:
                normalized_public.add(service_key)
    public_services.update(normalized_public)
    metadata["public_services"] = sorted(public_services)

    services = []
    for key, raw in document["services"].items():
        env = _normalize_environment(raw.get("environment") or {})
        depends = list((raw.get("depends_on") or {}).keys()) if isinstance(raw.get("depends_on"), dict) else list(raw.get("depends_on") or [])
        volumes = []
        for vol in raw.get("volumes") or []:
            if isinstance(vol, str):
                source, sep, target = vol.partition(":")
                if not sep:
                    raise ApplicationPlanError(f"Compose volume {vol!r} on {key!r} must specify a target.")
                if source.startswith("/") or source.startswith("."):
                    raise ApplicationPlanError(f"Catalog bind mount {vol!r} on {key!r} is not allowed; use a named persistent volume.")
                volumes.append({"source": source, "target": target, "mode": "rw", "mount_type": "volume"})
            else:
                source = str(vol.get("source") or "")
                mount_type = str(vol.get("type") or "volume")
                if mount_type != "volume":
                    raise ApplicationPlanError(f"Catalog volume type {mount_type!r} on {key!r} is unsupported.")
                volumes.append({"source": source or str(key), "target": str(vol["target"]), "mode": "ro" if vol.get("read_only") else "rw", "mount_type": "volume"})
        public = bool(raw.get("x-passdeployer", {}).get("public", False)) or key in public_services
        ports = raw.get("ports") or raw.get("expose") or []
        port_target = None
        if ports:
            first = ports[0]
            if isinstance(first, int):
                port_target = first
            elif isinstance(first, dict):
                port_target = int(first.get("target") or first.get("published") or 0) or None
            else:
                text = str(first)
                host, sep, target = text.partition(":")
                port_target = int(target.split("/")[0] if sep else host.split("/")[0])
                if sep and host and not public:
                    raise ApplicationPlanError(f"Catalog service {key!r} publishes a host port but is not declared public.")
        role = str((raw.get("x-passdeployer") or {}).get("role") or "")
        if not role:
            low = str(key).lower()
            if any(x in low for x in ("postgres", "mysql", "mariadb", "mongo", "database", "db")):
                role = "database"
            elif "redis" in low or "valkey" in low:
                role = "cache"
            elif "worker" in low:
                role = "worker"
            elif "scheduler" in low or "cron" in low:
                role = "scheduler"
            elif key in public_services or public:
                role = "app"
            else:
                role = "internal"
        health = raw.get("healthcheck")
        readiness_path = (raw.get("x-passdeployer") or {}).get("readiness_path")
        if not readiness_path and isinstance(health, dict) and health.get("test"):
            test = health.get("test")
            text = " ".join(str(x) for x in test)
            m = re.search(r"https?://(?:127\.0\.0\.1|localhost):\d+([^\s\"']*)", text)
            if m:
                readiness_path = m.group(1) or "/"
        inline_dockerfile = (raw.get("x-passdeployer") or {}).get("dockerfile")
        if raw.get("build") and not inline_dockerfile:
            raise ApplicationPlanError(
                f"Compose service {key!r} uses an external build context, which this catalog importer cannot safely materialize yet."
            )
        services.append({
            "key": str(key),
            "name_template": str((raw.get("x-passdeployer") or {}).get("name") or key),
            "role": role,
            "platform": "docker",
            "plan_type": "APP",
            "depends_on": depends,
            "image_template": _transform(raw.get("image"), render_context, aliases) if raw.get("image") else "",
            "dockerfile": _transform(str(inline_dockerfile), render_context, aliases) if inline_dockerfile else None,
            "files": {},
            "environment": _transform(env, render_context, aliases),
            "ports": raw.get("ports") or raw.get("expose") or [],
            "port": port_target,
            "volumes": volumes,
            "command": raw.get("command") or [],
            "entrypoint": raw.get("entrypoint") or [],
            "restart_policy": {"Name": str(raw.get("restart"))} if raw.get("restart") else {},
            "healthcheck": deepcopy(health) if isinstance(health, dict) else None,
            "working_directory": raw.get("working_dir"),
            "healthcheck_path": readiness_path,
            "healthcheck_timeout": _duration_seconds((health or {}).get("timeout"), 5) if isinstance(health, dict) else 5,
            "public": public,
            "required": bool((raw.get("x-passdeployer") or {}).get("required", True)),
            "labels": {str(k): str(v) for k, v in ((raw.get("labels") or {}).items())},
        })
    return {
        "catalog_id": catalog_id,
        "definition_version": str(metadata.get("definition_version") or "1"),
        "software_version": str(version),
        "variant_id": variant,
        "config": dict(config),
        "secrets": dict(secrets),
        "services": services,
        "networks": ["default"],
        "metadata": metadata,
        "fields": _meta_fields(metadata, variables),
    }
