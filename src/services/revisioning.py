"""Service-centric revision compiler and activation helpers."""
from __future__ import annotations

from copy import deepcopy
from django.core.files import File
import hashlib
import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from services.ports import sync_endpoint_reservation

from services.models import (
    Service,
    ServiceProcess,
    ServiceRevision,
    ServiceEnvironmentVariable,
    ServiceSecret,
    ServiceEndpoint,
)


_SENSITIVE_KEY_TOKENS = (
    "password",
    "secret",
    "token",
    "private_key",
    "api_key",
    "apikey",
    "signing_key",
    "authorization",
    "credential",
)


def _is_sensitive_key(key: object) -> bool:
    lowered = str(key).strip().lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _secret_name(path: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", path.upper()).strip("_")
    raw = raw[:100] or "VALUE"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:10].upper()
    return f"LEGACY_{raw}_{digest}"[:128]


def redact_config(value: Any) -> tuple[Any, list[str]]:
    """Return a recursively redacted copy and the paths that contain secrets."""
    secret_keys: list[str] = []

    def walk(node: Any, path: str = "") -> Any:
        if isinstance(node, dict):
            output = {}
            for key, item in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if _is_sensitive_key(key):
                    output[key] = "[SECRET_REF]"
                    secret_keys.append(key_path)
                else:
                    output[key] = walk(item, key_path)
            return output
        if isinstance(node, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return deepcopy(node)

    return walk(value or {}), sorted(set(secret_keys))


def _normalize_process_specs(service: Service, config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("processes")

    if isinstance(raw, dict):
        raw = [
            {"name": name, **(value if isinstance(value, dict) else {"command": value})}
            for name, value in raw.items()
        ]

    if isinstance(raw, list):
        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("type") or "").strip()
            if not name:
                continue
            replicas = int(item.get("replicas") or 1)
            if replicas != 1:
                raise ValueError("PassDeployer currently supports exactly one replica per process.")
            normalized.append(
                {
                    "name": name[:64],
                    "process_type": str(item.get("process_type") or item.get("type") or "custom")[:32],
                    "command": item.get("command"),
                    "entrypoint": item.get("entrypoint"),
                    "replicas": replicas,
                    "enabled": bool(item.get("enabled", True)),
                    "environment": dict(item.get("environment") or {}),
                    "healthcheck": dict(item.get("healthcheck") or {}),
                    "resources": dict(item.get("resources") or {}),
                    "metadata": dict(item.get("metadata") or {}),
                }
            )
        if normalized:
            return normalized

    existing = list(ServiceProcess.objects.filter(service=service).order_by("created_at", "name"))
    if existing:
        return [process.to_snapshot() for process in existing]

    specs = [
        {
            "name": "web",
            "process_type": "web",
            "command": config.get("start_command"),
            "entrypoint": config.get("entry_point"),
            "replicas": 1,
            "enabled": True,
            "environment": {},
            "healthcheck": {},
            "resources": dict(config.get("resource_limits") or {}),
            "metadata": {},
        }
    ]
    if bool(config.get("celery")):
        specs.append(
            {
                "name": "worker",
                "process_type": "worker",
                "command": config.get("worker_command") or "celery -A $CELERY_APP worker",
                "entrypoint": None,
                "replicas": 1,
                "enabled": True,
                "environment": {},
                "healthcheck": {},
                "resources": dict(config.get("resource_limits") or {}),
                "metadata": {"derived_from_legacy_celery": True},
            }
        )
        if bool(config.get("celery_beat")):
            specs.append(
                {
                    "name": "scheduler",
                    "process_type": "scheduler",
                    "command": config.get("scheduler_command") or "celery -A $CELERY_APP beat",
                    "entrypoint": None,
                    "replicas": 1,
                    "enabled": True,
                    "environment": {},
                    "healthcheck": {},
                    "resources": {},
                    "metadata": {"derived_from_legacy_celery_beat": True},
                }
            )
    return specs


def _sync_processes(service: Service, specs: list[dict[str, Any]]) -> None:
    for spec in specs:
        ServiceProcess.objects.update_or_create(
            service=service,
            name=spec["name"],
            defaults={
                "process_type": spec["process_type"],
                "command": spec.get("command"),
                "entrypoint": spec.get("entrypoint"),
                "replicas": spec.get("replicas", 1),
                "enabled": spec.get("enabled", True),
                "environment": spec.get("environment") or {},
                "healthcheck": spec.get("healthcheck") or {},
                "resources": spec.get("resources") or {},
                "metadata": spec.get("metadata") or {},
            },
        )


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = root
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _get_or_create_secret(
    service: Service,
    key: str,
    value: str,
    *,
    created_by=None,
    note: str = "",
) -> tuple[ServiceSecret, int]:
    from services.secret_store import encrypt_secret
    with transaction.atomic():
        secret = (
            ServiceSecret.objects
            .select_for_update()
            .filter(service=service, key=key)
            .first()
        )
        if secret is None:
            secret = ServiceSecret.objects.create(service=service, key=key, current_version=0)

        current = secret.get_current_value() if secret.current_version else ""
        if current != str(value or ""):
            next_version = secret.current_version + 1
            secret.versions.create(
                version=next_version,
                ciphertext=encrypt_secret(str(value or "")),
                created_by=created_by,
                note=note,
            )
            secret.current_version = next_version
            secret.save(update_fields=["current_version", "updated_at"])
        return secret, secret.current_version


def _extract_and_store_secrets(
    service: Service,
    config: dict[str, Any],
    *,
    created_by=None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []

    def walk(node: Any, path: str = "") -> Any:
        if isinstance(node, dict):
            output = {}
            for key, value in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if _is_sensitive_key(key) and value not in (None, "") and not isinstance(value, (dict, list)):
                    secret_key = _secret_name(key_path)
                    secret, version = _get_or_create_secret(
                        service,
                        secret_key,
                        str(value),
                        created_by=created_by,
                        note=f"Imported from legacy deployment path {key_path}",
                    )
                    refs.append({"path": key_path, "key": secret.key, "version": version})
                    output[key] = "[SECRET_REF]"
                else:
                    output[key] = walk(value, key_path)
            return output
        if isinstance(node, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return deepcopy(node)

    return walk(config), refs


def _service_environment_snapshot(
    service: Service,
    *,
    refs: list[dict[str, Any]],
    environment: dict[str, Any],
    created_by=None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in ServiceEnvironmentVariable.objects.filter(service=service, enabled=True).select_related("secret"):
        if row.secret_id:
            if row.scope in {ServiceEnvironmentVariable.Scope.BUILD, ServiceEnvironmentVariable.Scope.BOTH}:
                raise ValueError(
                    f"Build-scoped secret {row.key!r} is not supported by the current Docker build backend. "
                    "Use a runtime-scoped secret until BuildKit secret mounts are enabled."
                )
            secret = row.secret
            version = secret.current_version
            refs.append(
                {
                    "path": f"env.{row.key}",
                    "key": secret.key,
                    "version": version,
                    "scope": row.scope,
                }
            )
            continue
        out[row.key] = {"value": row.resolve_value(), "scope": row.scope}
    for key, value in (environment or {}).items():
        if key not in out:
            out[str(key)] = {"value": str(value), "scope": ServiceEnvironmentVariable.Scope.RUNTIME}
    return out


def _materialize_refs(root: dict[str, Any], revision: ServiceRevision) -> dict[str, Any]:
    from services.secret_store import decrypt_secret

    out = deepcopy(root or {})
    out.setdefault("env", {})
    out.setdefault("build_env", {})
    for ref in revision.secret_refs or []:
        secret = ServiceSecret.objects.filter(
            service_id=revision.service_id,
            key=ref.get("key"),
        ).first()
        if secret is None:
            raise ValueError(f"Revision secret {ref.get('key')!r} no longer exists.")
        version = secret.versions.filter(version=int(ref.get("version") or 0)).first()
        if version is None:
            raise ValueError(f"Revision secret version {ref.get('key')}:{ref.get('version')} no longer exists.")
        value = decrypt_secret(version.ciphertext)
        scope = str(ref.get("scope") or "runtime").lower()
        parts = str(ref.get("path") or "").split(".")
        if parts and parts[0] == "env":
            key = parts[-1]
            if scope in {"runtime", "both"}:
                out["env"][key] = value
            if scope in {"build", "both"}:
                out["build_env"][key] = value
        else:
            _set_path(out, str(ref.get("path") or ""), value)

    # Non-secret environment values retain their declared scope.
    for key, item in (revision.environment_snapshot or {}).items():
        if isinstance(item, dict):
            value = str(item.get("value") or "")
            scope = str(item.get("scope") or "runtime").lower()
        else:
            value = str(item)
            scope = "runtime"
        if scope in {"runtime", "both"}:
            out["env"][key] = value
        if scope in {"build", "both"}:
            out["build_env"][key] = value
    return out


def _database_environment_snapshot(
    service: Service,
    *,
    created_by=None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Resolve DB bindings into safe connection env plus versioned secrets."""
    from services.models import DatabaseResource, ServiceDatabaseBinding

    values: dict[str, str] = {}
    refs: list[dict[str, Any]] = []
    bindings = (
        ServiceDatabaseBinding.objects
        .filter(service=service)
        .select_related("database")
        .order_by("alias")
    )
    for binding in bindings:
        database = binding.database
        policy = dict(database.access_policy or {})
        allowed = policy.get("allowed_service_ids") or policy.get("allowed_services")
        if allowed:
            allowed_ids = {str(item) for item in allowed}
            if str(service.pk) not in allowed_ids:
                raise PermissionError(
                    f"Service {service.pk} is not allowed to access database resource {database.pk}."
                )
        if bool(policy.get("read_only")) and str(binding.access_mode).lower() == "rw":
            raise PermissionError(
                f"Database binding {binding.alias!r} requires read-only access."
            )

        prefix = str(binding.env_prefix or "DB").strip().upper()
        if not prefix:
            prefix = "DB"

        plain = {
            f"{prefix}_HOST": str(database.host or ""),
            f"{prefix}_PORT": str(database.port or ""),
            f"{prefix}_NAME": str(database.database_name or ""),
            f"{prefix}_DATABASE": str(database.database_name or ""),
            f"{prefix}_ENGINE": str(database.engine or ""),
        }
        for key, value in plain.items():
            if value:
                values[key] = value

        credential = getattr(database, "credential", None)
        if credential is not None:
            if credential.username:
                values[f"{prefix}_USER"] = str(credential.username)
                values[f"{prefix}_USERNAME"] = str(credential.username)
            if credential.password_ciphertext:
                secret_key = f"{prefix}_PASSWORD"
                secret, version = _get_or_create_secret(
                    service,
                    secret_key,
                    credential.get_password(),
                    created_by=created_by,
                    note=f"Database binding {binding.alias} password",
                )
                refs.append({
                    "path": f"env.{secret_key}",
                    "key": secret.key,
                    "version": version,
                    "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                })
    return values, refs


def materialize_revision_config(revision: ServiceRevision) -> dict[str, Any]:
    """Resolve one immutable revision into the legacy DeploymentConfig shape."""
    cfg = deepcopy(revision.config_snapshot or {})
    cfg.update(deepcopy(revision.runtime_snapshot or {}))
    cfg.setdefault("source", deepcopy(revision.source_snapshot or {}))
    cfg.setdefault("build", deepcopy(revision.build_snapshot or {}))
    if revision.process_snapshot:
        cfg["processes"] = deepcopy(revision.process_snapshot)
    if revision.endpoint_snapshot:
        cfg["endpoints"] = deepcopy(revision.endpoint_snapshot)
    if revision.volume_snapshot:
        cfg["volumes"] = deepcopy(revision.volume_snapshot)
    if revision.network_snapshot:
        cfg["networks"] = deepcopy(revision.network_snapshot)

    # Resolve secret refs LAST so redacted runtime/source snapshots can never
    # overwrite the exact secret version selected by this revision.
    return _materialize_refs(cfg, revision)




def _sync_legacy_endpoints(service: Service, config: dict[str, Any], *, public_default: bool = False) -> None:
    """Import legacy Deploy.config ports into first-class ServiceEndpoint rows."""
    if ServiceEndpoint.objects.filter(service=service).exists():
        return
    raw_ports = config.get("endpoints") or config.get("ports") or []
    if isinstance(raw_ports, dict):
        raw_ports = list(raw_ports.values())
    if not isinstance(raw_ports, list):
        return

    for index, raw in enumerate(raw_ports):
        try:
            if isinstance(raw, dict):
                target = int(raw.get("target") or raw.get("target_port") or raw.get("published"))
                published = raw.get("published")
                protocol = str(raw.get("protocol") or "tcp").lower()
                hostname = str(raw.get("hostname") or config.get("public_host") or config.get("domain") or "")
                exposure = str(raw.get("exposure") or ("public" if public_default or raw.get("public") else "internal")).lower()
            elif isinstance(raw, int):
                target = int(raw)
                published = None
                protocol = "tcp"
                hostname = str(config.get("public_host") or config.get("domain") or "")
                exposure = "public" if public_default else "internal"
            else:
                text_value = str(raw)
                parts = text_value.split(":")
                endpoint = parts[-1]
                protocol = "tcp"
                if "/" in endpoint:
                    endpoint, protocol = endpoint.split("/", 1)
                target = int(endpoint)
                published = int(parts[-2]) if len(parts) > 1 and parts[-2].isdigit() else None
                hostname = str(config.get("public_host") or config.get("domain") or "")
                exposure = "public" if public_default else "internal"
        except (TypeError, ValueError):
            continue

        endpoint, _ = ServiceEndpoint.objects.update_or_create(
            service=service,
            name=f"legacy-{target}-{protocol}-{index}",
            defaults={
                "target_port": target,
                "published_port": int(published) if published not in (None, "") else None,
                "protocol": protocol if protocol in {"tcp", "udp"} else "tcp",
                "exposure": exposure if exposure in {"public", "internal"} else "internal",
                "hostname": hostname if exposure == "public" else "",
                "tls": bool(config.get("tls")),
                "enabled": True,
                "metadata": {"migrated_from_deploy_config": True},
            },
        )
        sync_endpoint_reservation(endpoint)


def _sync_legacy_environment(service: Service, config: dict[str, Any], refs: list[dict[str, Any]], *, created_by=None) -> None:
    """Move legacy env values into ServiceEnvironmentVariable rows."""
    environment = dict(config.get("env") or config.get("environment") or {})
    for key, value in environment.items():
        key = str(key)
        secret_ref = next(
            (
                ref for ref in refs
                if ref.get("path") == f"env.{key}"
            ),
            None,
        )
        if secret_ref:
            secret = ServiceSecret.objects.get(service=service, key=secret_ref["key"])
            defaults = {
                "secret": secret,
                "value": "",
                "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                "enabled": True,
            }
        else:
            defaults = {
                "secret": None,
                "value": str(value),
                "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                "enabled": True,
            }
        ServiceEnvironmentVariable.objects.update_or_create(
            service=service,
            key=key[:128],
            defaults=defaults,
        )

@transaction.atomic
def ensure_revision_for_deploy(deploy, *, force_new: bool = False):
    """Compile the mutable Service domain into an immutable executable revision."""
    from deploy.models import Deploy

    deploy = (
        Deploy.objects.select_for_update()
        .select_related("service", "created_by")
        .get(pk=deploy.pk)
    )
    if deploy.revision_id and not force_new:
        return deploy

    service = Service.objects.select_for_update().get(pk=deploy.service_id)
    legacy_config = deepcopy(deploy.config) if isinstance(deploy.config, dict) else {}

    # Service-owned configuration is authoritative. Legacy Deploy.config is
    # retained as a migration fallback for fields that haven't moved yet.
    compiled: dict[str, Any] = deepcopy(legacy_config)
    compiled.update(deepcopy(service.source_config or {}))
    compiled.update(deepcopy(service.build_config or {}))
    compiled.update(deepcopy(service.runtime_config or {}))
    compiled["source_kind"] = service.source_kind

    # Convert old plaintext secrets in Deploy.config into versioned ServiceSecret rows.
    compiled, secret_refs = _extract_and_store_secrets(
        service,
        compiled,
        created_by=deploy.created_by,
    )

    _sync_legacy_endpoints(service, compiled, public_default=bool(compiled.get("public") or compiled.get("public_host") or compiled.get("domain")))
    _sync_legacy_environment(service, compiled, secret_refs, created_by=deploy.created_by)

    environment = dict(compiled.get("env") or compiled.get("environment") or {})
    database_environment, database_secret_refs = _database_environment_snapshot(
        service,
        created_by=deploy.created_by,
    )
    for key, value in database_environment.items():
        if key in environment and str(environment[key]) != str(value):
            raise ValueError(
                f"Environment variable {key!r} conflicts with a database binding. "
                "Rename the application variable or change the binding prefix."
            )
        environment.setdefault(key, value)
    secret_refs.extend(database_secret_refs)
    environment_snapshot = _service_environment_snapshot(
        service,
        refs=secret_refs,
        environment=environment,
        created_by=deploy.created_by,
    )

    process_specs = _normalize_process_specs(service, compiled)
    _sync_processes(service, process_specs)

    endpoints = [
        {
            "name": row.name,
            "process": row.process.name if row.process_id else None,
            "target_port": row.target_port,
            "published_port": row.published_port,
            "protocol": row.protocol,
            "exposure": row.exposure,
            "hostname": row.hostname,
            "path": row.path,
            "tls": row.tls,
            "enabled": row.enabled,
            "metadata": dict(row.metadata or {}),
        }
        for row in service.endpoints.filter(enabled=True).select_related("process").order_by("name")
    ]

    volumes = [
        {
            "source": row.get_docker_volume_name(),
            "target": row.get_bind_for_service(service),
            "mode": row.get_mode_for_service(service) or "rw",
            "size_mb": row.size_mb,
        }
        for row in service.volumes.all()
        if row.is_mounted_on_service(service)
    ]

    networks = []
    if service.network_id:
        networks.append(service.network.get_docker_network_name())
    for attachment in service.network_attachments.select_related("network").all():
        docker_name = attachment.network.get_docker_network_name()
        if docker_name not in networks:
            networks.append(docker_name)

    safe_snapshot = compiled
    redacted_snapshot, secret_keys = redact_config(safe_snapshot)
    redacted_source, _ = redact_config(service.source_config or {})
    redacted_build, _ = redact_config(service.build_config or {})
    redacted_runtime, _ = redact_config(service.runtime_config or {})
    previous = ServiceRevision.objects.filter(service=service).order_by("-revision_number").first()
    next_number = (previous.revision_number if previous else 0) + 1

    graph = {
        "processes": process_specs,
        "endpoints": endpoints,
        "volumes": volumes,
        "networks": networks,
    }

    revision = ServiceRevision.objects.create(
        service=service,
        revision_number=next_number,
        source_deploy=deploy,
        state=ServiceRevision.State.CREATED,
        config_snapshot=redacted_snapshot,
        process_snapshot=process_specs,
        secret_keys=secret_keys,
        secret_refs=secret_refs,
        source_snapshot=redacted_source,
        build_snapshot=redacted_build,
        runtime_snapshot=redacted_runtime,
        environment_snapshot=environment_snapshot,
        endpoint_snapshot=endpoints,
        volume_snapshot=volumes,
        network_snapshot=networks,
        graph_snapshot=graph,
        created_by=deploy.created_by,
    )

    # Capture the deployable archive into revision-owned storage. The legacy
    # Deploy row remains provenance only; deleting it must not break rollback.
    if deploy.zip_file:
        deploy.zip_file.open("rb")
        try:
            revision.artifact_file.save(
                f"{deploy.name}.zip",
                File(deploy.zip_file.file),
                save=False,
            )
        finally:
            try:
                deploy.zip_file.close()
            except Exception:
                pass
        revision.save(update_fields=["artifact_file", "updated_at"])

    Deploy.objects.filter(
        pk=deploy.pk
    ).update(
        revision=revision,
        config=redacted_snapshot,
    )
    deploy.revision = revision
    deploy.config = redacted_snapshot
    return deploy


@transaction.atomic
def mark_revision_failed(revision_id) -> None:
    revision = (
        ServiceRevision.objects.select_for_update()
        .filter(pk=revision_id)
        .first()
    )
    if revision is None or revision.state == ServiceRevision.State.ACTIVE:
        return
    revision.state = ServiceRevision.State.FAILED
    revision.save(update_fields=["state", "updated_at"])


@transaction.atomic
def get_active_revision(service: Service, *, for_update: bool = False) -> ServiceRevision | None:
    """Return the runtime-authoritative revision for a Service."""
    qs = ServiceRevision.objects.select_related("source_deploy")
    if for_update:
        qs = qs.select_for_update()
    revision = qs.filter(service_id=service.pk, pk=getattr(service, "active_revision_id", None)).first()
    if revision is not None:
        return revision

    # One-way compatibility bridge for pre-revision services.
    legacy_deploy = getattr(service, "selected_deploy", None)
    legacy_revision_id = getattr(legacy_deploy, "revision_id", None)
    if legacy_revision_id:
        revision = qs.filter(service_id=service.pk, pk=legacy_revision_id).first()
        if revision is not None:
            Service.objects.filter(pk=service.pk, active_revision_id__isnull=True).update(active_revision=revision)
            return revision
    return None


def get_active_deploy(service: Service, *, for_update: bool = False):
    revision = get_active_revision(service, for_update=for_update)
    if revision is None:
        return None
    return revision.source_deploy or revision.deployments.order_by("-created_at").first()


def activate_revision_locked(service: Service, revision_id) -> ServiceRevision:
    revision = (
        ServiceRevision.objects.select_for_update()
        .filter(pk=revision_id, service_id=service.pk)
        .first()
    )
    if revision is None:
        raise ValueError("Deployment references a revision that does not belong to this service.")

    ServiceRevision.objects.filter(
        service=service,
        state=ServiceRevision.State.ACTIVE,
    ).exclude(pk=revision.pk).update(state=ServiceRevision.State.SUPERSEDED)

    revision.state = ServiceRevision.State.ACTIVE
    revision.activated_at = timezone.now()
    revision.save(update_fields=["state", "activated_at", "updated_at"])

    Service.objects.filter(pk=service.pk).update(active_revision=revision)
    service.active_revision = revision
    return revision
