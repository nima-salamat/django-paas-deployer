from __future__ import annotations

import copy
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError
from django.utils.text import slugify

from plans.models import Plan
from services.models import PrivateNetwork, Service, ServiceProcess, ServiceEnvironmentVariable, ServiceSecret, Volume, ServiceEndpoint
from deploy.models import Deploy
from deploy.naming import allocate_deploy_name
from core.global_settings.config import PlanTypeChoices, SERVICE_STATUS_CHOICES
from .catalog import ApplicationCatalog, CatalogValidationError, is_public_definition, resolve_variant
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from services.ports import sync_endpoint_reservation
from .plan import plan_from_resolved
import shlex


_NAME_RE = re.compile(r"[^a-z0-9-]+")


class ApplicationNameConflict(CatalogValidationError):
    """Raised when a user concurrently claims an existing application slug."""

    def __init__(self, message: str, existing_installation_id: str | None = None):
        super().__init__(message)
        self.existing_installation_id = existing_installation_id


@dataclass(frozen=True)
class InstalledApplicationPlan:
    instance: ApplicationInstance
    definition: object
    resolved: dict


def safe_slug(value: str) -> str:
    s = slugify(value or "app")[:42].strip("-") or "app"
    return s


_PLATFORM_PUBLIC_HOST_TOKEN = "__PASSDEPLOYER_PUBLIC_HOST__"


def _service_public_host(service: Service) -> str:
    """Return the canonical public host derived from the created Service id."""
    from services.serializers import _service_host

    host = str(_service_host(service) or "").strip().lower().rstrip(".")
    if not host:
        raise CatalogValidationError("The platform deployment domain is not configured.")
    return host


def prepare_application_resolution(definition, variant_id: str, name: str, config: dict | None = None, *, public: bool = False) -> dict:
    """Resolve an app from user inputs while applying platform-owned controls."""
    requested = dict(config or {})
    if len(str(name or "").strip()) > 50:
        raise CatalogValidationError("Application name must be 50 characters or fewer.")
    if public:
        variant = definition.variants.get(str(variant_id)) or {}
        domain_field = next(
            (field for field in (variant.get("fields") or []) if str(field.get("id")) == "domain"),
            None,
        )
        if domain_field is None:
            raise CatalogValidationError("Public Ready Apps must define a platform-managed domain field.")
        if domain_field.get("user_editable", True) is not False:
            raise CatalogValidationError("Public Ready App domain fields must be platform-managed.")
        supplied_domain = requested.get("domain")
        if supplied_domain not in (None, ""):
            raise CatalogValidationError("The public hostname is assigned automatically after the application is created.")
        # Resolve with an internal placeholder. The real hostname depends on
        # the id of the newly created public Service.
        requested["domain"] = _PLATFORM_PUBLIC_HOST_TOKEN
    resolved = resolve_variant(definition, str(variant_id), requested)
    resolved["config"]["slug"] = safe_slug(name)
    if public:
        resolved["config"]["domain"] = _PLATFORM_PUBLIC_HOST_TOKEN
        resolved["config"]["https"] = True
    return resolved


def resource_summary_for_resolved(resolved: dict, base_plan: Plan) -> dict:
    """Validate child-plan allocation and return a server-authoritative preview."""
    application_plan = plan_from_resolved(resolved)
    services = []
    total_storage = 0
    total_cpu = 0.0
    total_ram = 0.0
    total_price = 0.0

    for spec in application_plan.services:
        assigned = _find_plan(
            base_plan=base_plan,
            platform=spec.platform,
            plan_type=spec.plan_type,
        )
        storage_mb = sum(
            _render_volume_size(volume.size_mb, config=resolved.get("config") or {}, secrets=resolved.get("secrets") or {})
            for volume in spec.volumes
        )
        limit_mb = int(float(assigned.max_storage or 0) * 1024)
        if storage_mb > limit_mb:
            raise CatalogValidationError(
                f"Service {spec.key!r} requires {storage_mb} MB of persistent storage, "
                f"but its selected plan allows {limit_mb} MB."
            )
        total_storage += storage_mb
        total_cpu += float(assigned.max_cpu or 0)
        total_ram += float(assigned.max_ram or 0)
        total_price += float(assigned.price_per_hour or 0)
        services.append({
            "name": _display_catalog_component_name(spec.key),
            "role": "database" if spec.role == "database" or spec.plan_type == str(PlanTypeChoices.DB) else "application",
            "platform": spec.platform,
            "plan": {
                "name": str(assigned.name),
                "plan_type": str(assigned.plan_type),
                "storage_type": str(assigned.storage_type),
            },
            "cpu_vcpu": float(assigned.max_cpu or 0),
            "ram_mb": float(assigned.max_ram or 0),
            "storage_mb": storage_mb,
            "storage_limit_mb": limit_mb,
            "volume_count": len(spec.volumes),
        })

    return {
        "service_count": len(services),
        "volume_count": sum(item["volume_count"] for item in services),
        "storage_mb": total_storage,
        "cpu_vcpu": total_cpu,
        "ram_mb": total_ram,
        "hourly_price": total_price,
        "services": services,
        "allocation_kind": "plan_limits",
    }


def application_services_for_cleanup(instance: ApplicationInstance):
    """Return application-owned Services and any unexpected network attachments.

    Bindings are the primary ownership source. The network plus immutable
    catalog metadata provide a legacy recovery path for installations that were
    partially deleted before child bindings could be removed.
    """
    bindings = list(
        instance.services.select_related("service", "deploy").all()
    )
    bound_service_ids = {str(binding.service_id) for binding in bindings}
    expected_keys = {
        str(spec.get("key"))
        for spec in ((instance.definition_snapshot or {}).get("_application_orchestration", {}).get("services") or [])
        if spec.get("key")
    }

    if instance.network_id:
        candidates = list(
            Service.objects.filter(
                user_id=instance.user_id,
                network_id=instance.network_id,
            ).order_by("created_at", "pk")
        )
    else:
        candidates = list(
            Service.objects.filter(
                user_id=instance.user_id,
                pk__in=[binding.service_id for binding in bindings],
            ).order_by("created_at", "pk")
        )

    owned = []
    unexpected = []
    seen = set()
    for service in candidates:
        service_id = str(service.pk)
        source = dict(service.source_config or {})
        application_owner = str(
            source.get("application_instance")
            or source.get("application_id")
            or ""
        )
        service_key = str(source.get("service_key") or "")
        catalog_id = str(source.get("catalog_id") or "")
        legacy_catalog_match = (
            service.source_kind == Service.SourceKind.CATALOG
            and catalog_id == str(instance.catalog_id)
            and service_key in expected_keys
        )
        if (
            service_id in bound_service_ids
            or application_owner == str(instance.pk)
            or legacy_catalog_match
        ):
            if service_id not in seen:
                owned.append(service)
                seen.add(service_id)
        else:
            unexpected.append(service)

    # A binding is authoritative even if a legacy/manual record temporarily
    # lacks the network relationship expected from the installed graph.
    for binding in bindings:
        service = binding.service
        if str(service.pk) not in seen:
            owned.append(service)
            seen.add(str(service.pk))

    return bindings, owned, unexpected


def _display_catalog_component_name(value: str) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text.title() or "Managed component"


def _catalog_service_name(user, application_slug: str, service_key: str, platform: str) -> str:
    """Build a readable, application-owned service name with platform suffix.

    Examples:
      my-deploy + wordpress + docker -> my-deploy-wordpress-docker
      my-deploy + mariadb + mariadb -> my-deploy-mariadb-mariadb

    Service.name is globally unique and limited to 30 characters, so any
    generated ordinal is inserted before the platform suffix to keep the
    platform visible at the end.
    """
    app_part = safe_slug(application_slug)
    component_part = safe_slug(service_key)
    platform_part = safe_slug(platform or "docker")
    suffix = f"-{platform_part}"
    prefix = f"{app_part}-{component_part}".strip("-")
    max_prefix = max(1, 30 - len(suffix))
    prefix = prefix[:max_prefix].rstrip("-") or "app"
    candidate = f"{prefix}{suffix}"[:30].rstrip("-")

    ordinal = 2
    while Service.objects.filter(name=candidate).exists():
        marker = f"-{ordinal}"
        available = max(1, 30 - len(suffix) - len(marker))
        base = prefix[:available].rstrip("-") or "app"
        candidate = f"{base}{marker}{suffix}"[:30].rstrip("-")
        ordinal += 1
    return candidate


def _render_volume_size(value, *, config: dict, secrets: dict) -> int:
    rendered = _render_service_value(str(value or 1024), config=config, secrets=secrets, service_hosts={})
    try:
        return max(1, int(rendered))
    except (TypeError, ValueError) as exc:
        raise CatalogValidationError(f"Invalid catalog volume size: {value!r}") from exc


def _find_plan(*, base_plan: Plan, platform: str, plan_type: str) -> Plan:
    plan_type = str(plan_type or PlanTypeChoices.APP)
    platform = str(platform or "docker").lower().strip()
    if plan_type in {str(PlanTypeChoices.APP), str(PlanTypeChoices.READY)}:
        if str(base_plan.platform) != "docker" or str(base_plan.plan_type) not in {
            str(PlanTypeChoices.APP), str(PlanTypeChoices.READY)
        }:
            raise CatalogValidationError("Choose an application plan that supports Docker/ready-made applications.")
        return base_plan
    if plan_type == str(PlanTypeChoices.DB):
        if platform == "docker":
            raise CatalogValidationError("Database catalog services must declare a database platform.")
        db_plan = Plan.objects.filter(platform=platform, plan_type=PlanTypeChoices.DB).order_by("id").first()
        if db_plan is None:
            raise CatalogValidationError(f"No database plan is configured for catalog database platform {platform!r}.")
        return db_plan
    raise CatalogValidationError(f"Unsupported catalog plan type: {plan_type}")


def _render_service_value(value: str, *, config: dict, secrets: dict, service_hosts: dict) -> str:
    if not isinstance(value, str):
        return value
    out = value
    for key, val in config.items():
        out = out.replace(f"${{config.{key}}}", str(val))
    for key, host in service_hosts.items():
        out = out.replace(f"${{service.{key}.host}}", str(host))

    # Public Ready Apps resolve their hostname only after the public Service
    # row has been created. Earlier resolution therefore leaves the platform
    # placeholder in rendered strings such as WP_HOME and SERVICE_URL_*.
    # Always replace that deferred value during the final service materialization
    # so application containers never receive the internal placeholder.
    public_host = config.get("domain")
    if public_host not in (None, "", _PLATFORM_PUBLIC_HOST_TOKEN):
        out = out.replace(_PLATFORM_PUBLIC_HOST_TOKEN, str(public_host))
    return out


_SECRET_REF_RE = re.compile(r"\$\{secret\.([A-Za-z0-9_]+)\}")


def _secret_references(value) -> set[str]:
    if isinstance(value, dict):
        refs = set()
        for item in value.values():
            refs.update(_secret_references(item))
        return refs
    if isinstance(value, (list, tuple)):
        refs = set()
        for item in value:
            refs.update(_secret_references(item))
        return refs
    if isinstance(value, str):
        return set(_SECRET_REF_RE.findall(value))
    return set()


def _render_secret_value(value: str, *, config: dict, secrets: dict, service_hosts: dict) -> str:
    rendered = _render_service_value(value, config=config, secrets={}, service_hosts=service_hosts)
    for key in _secret_references(rendered):
        if key not in secrets:
            raise CatalogValidationError(f"Catalog references unknown secret {key!r}.")
        rendered = rendered.replace(f"${{secret.{key}}}", str(secrets[key]))
    return rendered


def _database_runtime_config(spec: dict, *, environment: dict) -> dict:
    if str(spec.get("role") or "") != "database" or str(spec.get("plan_type") or "") != str(PlanTypeChoices.DB):
        return {}
    platform = str(spec.get("platform") or "").lower()
    normalized = {str(k).upper(): v for k, v in environment.items()}
    username = spec.get("database_username")
    database = spec.get("database_name")
    password = spec.get("password")
    root_password = spec.get("root_password")

    # MySQL and MariaDB images accept both MYSQL_* and MARIADB_* variable
    # families. Ready App definitions historically use both spellings, so the
    # normalized DB contract must read from either family rather than relying
    # on the selected image's preferred prefix.
    if platform in {"mysql", "mariadb"}:
        prefixes = ("MYSQL", "MARIADB")
    else:
        prefix = {
            "postgresql": "POSTGRES",
            "postgres": "POSTGRES",
            "mongodb": "MONGO",
            "mongo": "MONGO",
            "oracle": "ORACLE",
        }.get(platform, "")
        prefixes = (prefix,) if prefix else ()

    for prefix in prefixes:
        username = username or normalized.get(f"{prefix}_USER") or normalized.get(f"{prefix}_USERNAME")
        database = database or normalized.get(f"{prefix}_DB") or normalized.get(f"{prefix}_DATABASE")
        password = password or normalized.get(f"{prefix}_PASSWORD")
        root_password = root_password or normalized.get(f"{prefix}_ROOT_PASSWORD")

    return {key: value for key, value in {
        "platform": platform, "username": username, "database": database,
        "password": password, "root_password": root_password,
    }.items() if value not in (None, "")}


def _write_archive(dockerfile: str, extra_files: dict[str, str] | None = None) -> ContentFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Dockerfile", dockerfile)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return ContentFile(buf.getvalue(), name="catalog-deployment.zip")


def _dockerfile_healthcheck(healthcheck: dict | None) -> str:
    if not healthcheck or healthcheck.get("disable"):
        return ""
    test = healthcheck.get("test")
    if not test:
        return ""
    def duration(value):
        if value in (None, ""):
            return None
        text = str(value).strip()
        if text[-1:] in {"s", "m", "h"}:
            return text
        return text + "s"
    opts = []
    for key in ("interval", "timeout", "start_period"):
        value = duration(healthcheck.get(key))
        if value:
            opts.append(f"--{key.replace('_', '-')}={value}")
    retries = healthcheck.get("retries")
    if retries not in (None, ""):
        opts.append(f"--retries={int(retries)}")
    if isinstance(test, list):
        parts = [str(x) for x in test]
        mode = parts[0] if parts else "CMD-SHELL"
        args = parts[1:]
        if mode == "CMD-SHELL":
            command = " ".join(args)
            return "HEALTHCHECK " + " ".join(opts) + " CMD-SHELL " + command
        if mode == "CMD":
            import json
            return "HEALTHCHECK " + " ".join(opts) + " CMD " + json.dumps(args)
        if mode == "NONE":
            return "HEALTHCHECK NONE"
    if isinstance(test, str):
        return "HEALTHCHECK " + " ".join(opts) + " CMD-SHELL " + test
    raise CatalogValidationError("Unsupported catalog healthcheck test format.")


def validate_install_request(user, payload: dict, *, require_public: bool = False) -> tuple[object, dict, Plan]:
    catalog_id = str(payload.get("catalog_id") or "").strip()
    variant_id = str(payload.get("variant") or "").strip()
    name = str(payload.get("name") or "").strip()
    plan_id = payload.get("plan_id")
    config = payload.get("config") or {}
    if not catalog_id or not variant_id or not name or not plan_id:
        raise CatalogValidationError("catalog_id, variant, name, plan_id, and config are required.")
    if len(name) > 50:
        raise CatalogValidationError("Application name must be 50 characters or fewer.")
    if not isinstance(config, dict):
        raise CatalogValidationError("config must be an object.")
    definition = ApplicationCatalog.get(catalog_id)
    if require_public and not is_public_definition(definition):
        raise CatalogValidationError("This application is not available in the Ready Apps catalog.")
    resolved = prepare_application_resolution(definition, variant_id, name, config, public=require_public)
    plan = Plan.objects.filter(pk=plan_id).first()
    if not plan or str(plan.platform) != "docker":
        raise CatalogValidationError("Selected plan must be a Docker application/ready-made plan.")
    resource_summary_for_resolved(resolved, plan)
    return definition, resolved, plan


def _create_application_installation(
    user,
    payload: dict,
    storage_artifacts: list[tuple[object, str]],
    *,
    require_public: bool = False,
) -> ApplicationInstance:
    definition, resolved, base_plan = validate_install_request(user, payload, require_public=require_public)
    requested_name = str(payload["name"]).strip()
    slug = safe_slug(requested_name)
    existing = ApplicationInstance.objects.filter(user=user, slug=slug).only("pk").first()
    if existing is not None:
        raise ApplicationNameConflict(
            "An application with this name already exists.",
            existing_installation_id=str(existing.pk),
        )

    network = PrivateNetwork.objects.create(
        user=user,
        name=f"{slug}-net"[:50],
        description=f"Private network for catalog application {requested_name}",
    )

    try:
        with transaction.atomic():
            instance = ApplicationInstance.objects.create(
                user=user,
                name=requested_name,
                slug=slug,
                catalog_id=definition.id,
                definition_version=definition.definition_version,
                software_version=definition.software_version,
                variant_id=str(payload["variant"]),
                definition_snapshot={
                    **copy.deepcopy(definition.data),
                    "_application_orchestration": {
                        "services": [
                            {
                                "key": str(spec["key"]),
                                "role": str(spec.get("role") or "app"),
                                "platform": str(spec.get("platform") or "docker"),
                                "plan_type": str(spec.get("plan_type") or PlanTypeChoices.APP),
                                "depends_on": [str(dep) for dep in (spec.get("depends_on") or [])],
                                "required": bool(spec.get("required", True)),
                            }
                            for spec in (resolved.get("services") or [])
                        ],
                    },
                },
                # The real public hostname is service-id based and is not
                # known until the child Services have been created.
                config={
                    str(key): value
                    for key, value in dict(resolved["config"]).items()
                    if str(key) != "domain"
                },
                # Generated secrets are persisted in ServiceSecret/ServiceSecretVersion.
                # Keep ApplicationInstance free of plaintext secret material.
                secret_config={},
                status=ApplicationStatus.PENDING,
                network=network,
            )
    except IntegrityError as exc:
        constraint = getattr(getattr(getattr(exc, "__cause__", None), "diag", None), "constraint_name", None)
        message = str(exc).lower()
        is_name_conflict = (
            constraint == "uniq_application_instance_user_slug"
            or ("unique constraint failed" in message and "user_id" in message and "slug" in message)
        )
        if not is_name_conflict:
            raise
        raise ApplicationNameConflict("An application with this name already exists.") from exc
    created_by = user
    service_rows = []
    for sequence, spec in enumerate(resolved["services"]):
        key = str(spec["key"])
        platform = str(spec["platform"])
        plan_type = str(spec.get("plan_type") or PlanTypeChoices.APP)
        plan = _find_plan(base_plan=base_plan, platform=platform, plan_type=plan_type)

        # Service.name is globally unique. The existence check in
        # _catalog_service_name() cannot by itself prevent two concurrent
        # transactions from selecting the same candidate, so retry only when
        # the database confirms the candidate lost a uniqueness race.
        service = None
        for _attempt in range(5):
            service_name = _catalog_service_name(user, slug, key, platform)
            try:
                with transaction.atomic():
                    service = Service.objects.create(
                        name=service_name,
                        user=user,
                        plan=plan,
                        network=network,
                        read_only=False,
                        status=SERVICE_STATUS_CHOICES.QUEUED,
                        source_kind=Service.SourceKind.CATALOG,
                        source_config={
                            "application_instance": str(instance.pk),
                            "catalog_id": definition.id,
                            "definition_version": definition.definition_version,
                            "software_version": definition.software_version,
                            "variant": str(payload["variant"]),
                            "service_key": key,
                        },
                        build_config={},
                        runtime_config={},
                        desired_state="running",
                    )
            except IntegrityError:
                # Only retry when this exact name now exists, which identifies
                # the concurrent global Service.name race. Other integrity
                # failures must remain visible to the caller.
                if Service.objects.filter(name=service_name).exists():
                    continue
                raise
            break

        if service is None:
            raise CatalogValidationError(
                f"Unable to allocate a unique Service name for catalog service {key!r}."
            )
        service_rows.append((sequence, spec, service, plan))

    service_hosts = {key: service.get_docker_service_name() for (_, spec, service, _) in service_rows for key in [str(spec["key"])]}
    public_service_hosts = {
        str(spec["key"]): _service_public_host(service)
        for _, spec, service, _ in service_rows
        if bool(spec.get("public", False))
    }
    primary_public_host = next(iter(public_service_hosts.values()), "")

    if primary_public_host:
        persisted_config = dict(instance.config or {})
        persisted_config["domain"] = primary_public_host
        instance.config = persisted_config
        instance.save(update_fields=["config"])

    for sequence, spec, service, plan in service_rows:
        key = str(spec["key"])
        plan_type = str(spec.get("plan_type") or PlanTypeChoices.APP)
        is_database = plan_type == str(PlanTypeChoices.DB)
        resolved_config = dict(resolved["config"])
        service_public_host = public_service_hosts.get(key, primary_public_host)
        if service_public_host:
            resolved_config["domain"] = service_public_host
        else:
            resolved_config.pop("domain", None)
        raw_environment = {str(k): str(v) for k, v in (spec.get("environment") or {}).items()}
        cfg = {
            "platform": str(spec.get("platform") or "docker") if is_database else "docker",
            "catalog_platform": str(spec.get("platform") or "docker"),
            "catalog_plan_type": plan_type,
            "catalog_id": definition.id,
            "catalog_definition_version": definition.definition_version,
            "catalog_software_version": definition.software_version,
            "catalog_variant": str(payload["variant"]),
            "catalog_service_key": key,
            "catalog_managed": True,
            "networks": [network.get_docker_network_name()],
            "labels": {
                "application.id": str(instance.pk),
                "application.service": key,
                "managed-by": "passdeployer",
                **{str(k): str(v) for k, v in (spec.get("labels") or {}).items()},
            },
            "working_directory": spec.get("working_directory"),
        }
        cfg.update(_database_runtime_config(spec, environment=raw_environment))
        env = {k: _render_service_value(v, config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts) for k, v in raw_environment.items()}

        from services.revisioning import _get_or_create_secret
        for secret_key in _secret_references(raw_environment):
            if secret_key not in resolved["secrets"]:
                raise CatalogValidationError(f"Catalog references unknown secret {secret_key!r}.")
            _get_or_create_secret(service, secret_key, str(resolved["secrets"][secret_key]), created_by=created_by, note=f"Catalog secret for {definition.id}:{key}")

        for env_key, raw_value in (spec.get("environment") or {}).items():
            text_value = str(raw_value)
            secret_match = re.fullmatch(r"\$\{secret\.([A-Za-z0-9_]+)\}", text_value)
            if secret_match:
                secret_key = secret_match.group(1)
                secret = ServiceSecret.objects.get(service=service, key=secret_key)
                ServiceEnvironmentVariable.objects.update_or_create(
                    service=service,
                    key=str(env_key),
                    defaults={
                        "secret": secret,
                        "value": "",
                        "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                        "enabled": True,
                    },
                )
            elif _secret_references(text_value):
                composite_key = "catalog_env_" + str(env_key).lower()
                rendered_value = _render_secret_value(text_value, config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts)
                composite_secret, _ = _get_or_create_secret(
                    service,
                    composite_key[:128],
                    rendered_value,
                    created_by=created_by,
                    note=f"Catalog composite environment secret for {definition.id}:{key}:{env_key}",
                )
                ServiceEnvironmentVariable.objects.update_or_create(
                    service=service,
                    key=str(env_key),
                    defaults={
                        "secret": composite_secret,
                        "value": "",
                        "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                        "enabled": True,
                    },
                )
            else:
                ServiceEnvironmentVariable.objects.update_or_create(
                    service=service,
                    key=str(env_key),
                    defaults={
                        "secret": None,
                        "value": _render_service_value(text_value, config=resolved_config, secrets={}, service_hosts=service_hosts),
                        "scope": ServiceEnvironmentVariable.Scope.RUNTIME,
                        "enabled": True,
                    },
                )

        healthcheck = spec.get("healthcheck") if isinstance(spec.get("healthcheck"), dict) else None
        unsupported_secret_locations = {
            "name_template": spec.get("name_template"),
            "command": spec.get("command"),
            "entrypoint": spec.get("entrypoint"),
            "ports": spec.get("ports"),
            "volumes": spec.get("volumes"),
            "labels": spec.get("labels"),
            "healthcheck": healthcheck,
        }
        for location, value in unsupported_secret_locations.items():
            if _secret_references(value):
                raise CatalogValidationError(
                    f"Catalog service {key} uses a secret in unsupported {location} metadata."
                )

        image_template = str(spec.get("image_template") or spec.get("image") or "")
        if _secret_references(image_template):
            raise CatalogValidationError(
                f"Catalog service {key} uses a secret in its image reference, which is unsupported."
            )
        image = _render_service_value(
            image_template,
            config=resolved_config,
            secrets={},
            service_hosts=service_hosts,
        )
        dockerfile = spec.get("dockerfile")
        is_database = plan_type == str(PlanTypeChoices.DB)
        if is_database:
            dockerfile_text = ""
            files = {}
        else:
            if dockerfile:
                dockerfile_text = _render_service_value(str(dockerfile), config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts).replace("$"+"{config.image_template}", image)
            elif image:
                dockerfile_text = f"FROM {image}\n"
            else:
                raise CatalogValidationError(f"Catalog service {key} must define an image or Dockerfile.")
            if "${secret." in dockerfile_text.lower():
                raise CatalogValidationError(f"Catalog service {key} attempts to bake a secret into its Dockerfile. Move the secret to a runtime environment variable instead.")
            healthcheck_instruction = _dockerfile_healthcheck(healthcheck)
            if healthcheck_instruction and "HEALTHCHECK" not in dockerfile_text:
                dockerfile_text = dockerfile_text.rstrip() + "\n" + healthcheck_instruction + "\n"

            # Apache-based catalog images should not emit the noisy
            # AH00558 startup warning. Keep this scoped to images that
            # explicitly identify Apache so unrelated images are untouched.
            if "apache" in image.lower() and "ServerName " not in dockerfile_text:
                dockerfile_text = (
                    dockerfile_text.rstrip()
                    + "\nRUN grep -q '^ServerName ' /etc/apache2/apache2.conf "
                    + "|| echo 'ServerName localhost' >> /etc/apache2/apache2.conf\n"
                )
            files = {}
            for name, content in (spec.get("files") or {}).items():
                if _secret_references(content):
                    raise CatalogValidationError(f"Catalog service {key} attempts to bake a secret into build file {name!r}. Move the secret to a runtime environment variable instead.")
                files[str(name)] = _render_service_value(str(content), config=resolved_config, secrets={}, service_hosts=service_hosts)

        public = bool(spec.get("public", False))
        port = spec.get("port")
        if public and not port:
            for first in spec.get("ports") or []:
                if isinstance(first, dict):
                    port = first.get("target") or first.get("published")
                elif isinstance(first, int):
                    port = first
                else:
                    text = str(first)
                    port = int(text.split(":")[-1].split("/")[0])
                if port:
                    break

        runtime_config = {
            "platform": str(spec.get("platform") or "docker") if is_database else "docker",
            "catalog_platform": str(spec.get("platform") or "docker"),
            "catalog_service_key": key,
            "catalog_managed": True,
            "start_command": (
                shlex.join(
                    [
                        _render_service_value(
                            str(x),
                            config=resolved_config,
                            secrets={},
                            service_hosts=service_hosts,
                        )
                        for x in (spec.get("command") or [])
                    ]
                )
                if isinstance(spec.get("command"), (list, tuple)) and spec.get("command")
                else (
                    _render_service_value(
                        str(spec.get("command")),
                        config=resolved_config,
                        secrets={},
                        service_hosts=service_hosts,
                    )
                    if spec.get("command")
                    else None
                )
            ),
            "entry_point": (
                shlex.join([str(x) for x in (spec.get("entrypoint") or [])])
                if isinstance(spec.get("entrypoint"), (list, tuple)) and spec.get("entrypoint")
                else (str(spec.get("entrypoint")) if spec.get("entrypoint") else None)
            ),
            "restart_policy": dict(spec.get("restart_policy") or {}),
            "working_directory": spec.get("working_directory"),
            "port": int(port) if port else None,
            "public": public,
            "public_host": service_public_host if public else None,
            "healthcheck": healthcheck,
            "healthcheck_path": spec.get("healthcheck_path"),
            "healthcheck_timeout": float(spec.get("healthcheck_timeout") or 5),
        }
        runtime_config.update(_database_runtime_config(spec, environment=raw_environment))
        for secret_key in _secret_references(runtime_config):
            if secret_key not in resolved["secrets"]:
                raise CatalogValidationError(f"Catalog references unknown secret {secret_key!r}.")
            _get_or_create_secret(service, secret_key, str(resolved["secrets"][secret_key]), created_by=created_by, note=f"Catalog runtime secret for {definition.id}:{key}")
        service.runtime_config = runtime_config
        service.build_config = {} if is_database else {
            "dockerfile_source": "archive",
            "dockerfile": dockerfile_text,
            "files": files,
        }
        service.save(update_fields=["runtime_config", "build_config", "updated_at"])

        raw_ports = list(spec.get("ports") or [])
        if not raw_ports and port:
            raw_ports = [{"target": int(port)}]
        for raw_port in raw_ports:
            if isinstance(raw_port, dict):
                target = int(raw_port.get("target") or raw_port.get("published"))
                published = raw_port.get("published")
                protocol = str(raw_port.get("protocol") or "tcp").lower()
            elif isinstance(raw_port, int):
                target = int(raw_port)
                published = None
                protocol = "tcp"
            else:
                text_value = str(raw_port)
                parts = text_value.split(":")
                endpoint_part = parts[-1]
                proto = "tcp"
                if "/" in endpoint_part:
                    endpoint_part, proto = endpoint_part.split("/", 1)
                target = int(endpoint_part)
                published = int(parts[-2]) if len(parts) >= 2 and parts[-2].isdigit() else None
                protocol = proto.lower()

            endpoint_row, _ = ServiceEndpoint.objects.update_or_create(
                service=service,
                name=f"port-{target}-{protocol}",
                defaults={
                    "target_port": target,
                    "published_port": int(published) if published not in (None, "") else None,
                    "protocol": protocol if protocol in {"tcp", "udp"} else "tcp",
                    "exposure": "public" if public else "internal",
                    "hostname": service_public_host if public else "",
                    "tls": bool(resolved_config.get("https") or False),
                    "enabled": True,
                    "metadata": {"catalog_service_key": key},
                },
            )
            sync_endpoint_reservation(endpoint_row)

        ServiceProcess.objects.update_or_create(
            service=service,
            name="web",
            defaults={
                "process_type": str(spec.get("role") or "web"),
                "command": runtime_config.get("start_command"),
                "entrypoint": runtime_config.get("entry_point"),
                "replicas": 1,
                "enabled": True,
                "environment": {},
                "healthcheck": healthcheck or {},
                "resources": {},
                "metadata": {"catalog_service_key": key},
            },
        )

        for volume_spec in spec.get("volumes") or []:
            bind = str(volume_spec.get("target") or "")
            if not bind:
                continue
            size_mb = _render_volume_size(volume_spec.get("size_mb"), config=resolved_config, secrets={})
            vol_name = f"cat-{service.id.hex[:8]}-{safe_slug(str(volume_spec.get('source') or bind))}"[:32]
            mode = str(volume_spec.get("mode") or "rw")
            volume, created = Volume.objects.get_or_create(
                name=vol_name,
                defaults={
                    "user": user,
                    "service": service,
                    "service_attachments": {str(service.id): {"bind": bind, "mode": mode}},
                    "default_bind": bind,
                    "default_mode": mode,
                    "size_mb": size_mb,
                },
            )
            if not created:
                # Catalog volume names are deterministic per installed service.
                # Reusing a row owned by another service/user would bypass the
                # exclusive ownership contract, while changing size would become
                # a DB-only resize once the Docker volume is provisioned.
                if str(volume.user_id) != str(user.id) or (
                    volume.service_id is not None and str(volume.service_id) != str(service.id)
                ):
                    raise CatalogValidationError(
                        f"Persistent volume {bind!r} is already owned by another service and cannot be reused."
                    )
                if int(volume.size_mb) != int(size_mb):
                    raise CatalogValidationError(
                        f"Persistent volume {bind!r} already has a declared size of {volume.size_mb} MB; catalog resize to {size_mb} MB is not supported."
                    )
                if volume.service_id is None:
                    volume.attach_to_service(service, bind=bind, mode=mode)

        deploy = Deploy(
            name=allocate_deploy_name(service),
            service=service,
            created_by=created_by,
            version=1.0,
            config=cfg,
            zip_file=None if is_database else _write_archive(dockerfile_text, files),
        )
        try:
            deploy.save()
        except Exception:
            if deploy.zip_file and deploy.zip_file.name:
                try:
                    deploy.zip_file.storage.delete(deploy.zip_file.name)
                except Exception:
                    pass
            raise
        if deploy.zip_file and deploy.zip_file.name:
            storage_artifacts.append((deploy.zip_file.storage, deploy.zip_file.name))
        ApplicationInstanceService.objects.create(
            instance=instance,
            service=service,
            deploy=deploy,
            service_key=key,
            sequence=sequence,
        )
    return instance


@transaction.atomic
def create_application_installation(
    user,
    payload: dict,
    *,
    require_public: bool = False,
) -> ApplicationInstance:
    storage_artifacts: list[tuple[object, str]] = []
    try:
        return _create_application_installation(
            user,
            payload,
            storage_artifacts,
            require_public=require_public,
        )
    except Exception:
        for storage, name in storage_artifacts:
            try:
                if storage.exists(name):
                    storage.delete(name)
            except Exception:
                pass
        raise
