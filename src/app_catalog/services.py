from __future__ import annotations

import copy
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from plans.models import Plan
from services.models import PrivateNetwork, Service, ServiceProcess, ServiceEnvironmentVariable, ServiceSecret, Volume, ServiceEndpoint
from deploy.models import Deploy
from deploy.naming import allocate_deploy_name
from core.global_settings.config import PlanTypeChoices
from .catalog import ApplicationCatalog, CatalogValidationError, resolve_variant
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from services.ports import sync_endpoint_reservation
from .plan import plan_from_resolved
import shlex


_NAME_RE = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True)
class InstalledApplicationPlan:
    instance: ApplicationInstance
    definition: object
    resolved: dict


def safe_slug(value: str) -> str:
    s = slugify(value or "app")[:42].strip("-") or "app"
    return s


def _unique_service_name(user, base: str) -> str:
    base = safe_slug(base)[:30]
    candidate = base
    i = 2
    while Service.objects.filter(name=candidate).exists():
        suffix = f"-{i}"
        candidate = (base[: 30 - len(suffix)] + suffix).strip("-")
        i += 1
    return candidate


def _render_volume_size(value, *, config: dict, secrets: dict) -> int:
    rendered = _render_service_value(str(value or 1024), config=config, secrets=secrets, service_hosts={})
    try:
        return max(1, int(rendered))
    except (TypeError, ValueError) as exc:
        raise CatalogValidationError(f"Invalid catalog volume size: {value!r}") from exc


def _find_plan(*, base_plan: Plan, platform: str, plan_type: str) -> Plan:
    # Catalog services are all executed by the generic Docker deployment
    # engine. The catalog platform is descriptive metadata, not a special
    # deployment implementation.
    if plan_type == str(PlanTypeChoices.APP):
        if str(base_plan.platform) != "docker" or str(base_plan.plan_type) not in {
            str(PlanTypeChoices.APP), str(PlanTypeChoices.READY)
        }:
            raise CatalogValidationError("Choose an application plan that supports Docker/ready-made applications.")
        return base_plan
    raise CatalogValidationError(f"Unsupported catalog plan type: {plan_type}")


def _render_service_value(value: str, *, config: dict, secrets: dict, service_hosts: dict) -> str:
    if not isinstance(value, str):
        return value
    out = value
    for key, val in config.items():
        out = out.replace(f"${{config.{key}}}", str(val))
    for key, val in secrets.items():
        out = out.replace(f"${{secret.{key}}}", str(val))
    for key, host in service_hosts.items():
        out = out.replace(f"${{service.{key}.host}}", str(host))
    return out


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


def validate_install_request(user, payload: dict) -> tuple[object, dict, Plan]:
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
    resolved = resolve_variant(definition, variant_id, config)
    plan_from_resolved(resolved)
    resolved["config"]["slug"] = safe_slug(name)
    plan = Plan.objects.filter(pk=plan_id).first()
    if not plan or str(plan.platform) != "docker":
        raise CatalogValidationError("Selected plan must be a Docker application/ready-made plan.")
    return definition, resolved, plan


@transaction.atomic
def create_application_installation(user, payload: dict) -> ApplicationInstance:
    definition, resolved, base_plan = validate_install_request(user, payload)
    requested_name = str(payload["name"]).strip()
    slug = safe_slug(requested_name)
    if ApplicationInstance.objects.filter(user=user, slug=slug).exists():
        raise CatalogValidationError("An application with this name already exists.")

    network = PrivateNetwork.objects.create(
        user=user,
        name=f"{slug}-net"[:50],
        description=f"Private network for catalog application {requested_name}",
    )

    instance = ApplicationInstance.objects.create(
        user=user,
        name=requested_name,
        slug=slug,
        catalog_id=definition.id,
        definition_version=definition.definition_version,
        software_version=definition.software_version,
        variant_id=str(payload["variant"]),
        definition_snapshot=copy.deepcopy(definition.data),
        config=dict(resolved["config"]),
        secret_config={},
        status=ApplicationStatus.PENDING,
        network=network,
    )

    created_by = user
    service_rows = []
    for sequence, spec in enumerate(resolved["services"]):
        key = str(spec["key"])
        platform = str(spec["platform"])
        plan_type = str(spec.get("plan_type") or PlanTypeChoices.APP)
        plan = _find_plan(base_plan=base_plan, platform=platform, plan_type=plan_type)
        service_name = _unique_service_name(user, _render_service_value(spec.get("name_template", key), config=resolved["config"], secrets=resolved["secrets"], service_hosts={}))
        service = Service.objects.create(
            name=service_name,
            user=user,
            plan=plan,
            network=network,
            read_only=False,
            source_kind=Service.SourceKind.CATALOG,
            source_config={
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
        service_rows.append((sequence, spec, service, plan))

    service_hosts = {key: service.get_docker_service_name() for (_, spec, service, _) in service_rows for key in [str(spec["key"])]}

    for sequence, spec, service, plan in service_rows:
        key = str(spec["key"])
        resolved_config = dict(resolved["config"])
        cfg = {
            "platform": "docker",
            "catalog_platform": str(spec.get("platform") or "docker"),
            "catalog_plan_type": str(spec.get("plan_type") or PlanTypeChoices.APP),
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
            "depends_on": list(spec.get("depends_on") or []),
            "required": bool(spec.get("required", True)),
            "working_directory": spec.get("working_directory"),
        }

        env = {
            k: _render_service_value(
                str(v),
                config=resolved_config,
                secrets=resolved["secrets"],
                service_hosts=service_hosts,
            )
            for k, v in (spec.get("environment") or {}).items()
        }

        from services.revisioning import _get_or_create_secret
        for secret_key, secret_value in (resolved.get("secrets") or {}).items():
            _get_or_create_secret(
                service,
                str(secret_key),
                str(secret_value),
                created_by=created_by,
                note=f"Catalog secret for {definition.id}:{key}",
            )

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

        image = _render_service_value(
            str(spec.get("image_template") or spec.get("image") or ""),
            config=resolved_config,
            secrets={},
            service_hosts=service_hosts,
        )
        dockerfile = spec.get("dockerfile")
        healthcheck = spec.get("healthcheck") if isinstance(spec.get("healthcheck"), dict) else None
        if dockerfile:
            dockerfile_text = _render_service_value(
                str(dockerfile),
                config=resolved_config,
                secrets=resolved["secrets"],
                service_hosts=service_hosts,
            ).replace("$"+"{config.image_template}", image)
        elif image:
            dockerfile_text = f"FROM {image}\n"
        else:
            raise CatalogValidationError(f"Catalog service {key} must define an image or Dockerfile.")

        if "${secret." in dockerfile_text.lower():
            raise CatalogValidationError(
                f"Catalog service {key} attempts to bake a secret into its Dockerfile. Move the secret to an environment variable instead."
            )

        healthcheck_instruction = _dockerfile_healthcheck(healthcheck)
        if healthcheck_instruction and "HEALTHCHECK" not in dockerfile_text:
            dockerfile_text = dockerfile_text.rstrip() + "\n" + healthcheck_instruction + "\n"

        files = {
            str(name): _render_service_value(
                str(content),
                config=resolved_config,
                secrets=resolved["secrets"],
                service_hosts=service_hosts,
            )
            for name, content in (spec.get("files") or {}).items()
        }

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
            "platform": "docker",
            "catalog_platform": str(spec.get("platform") or "docker"),
            "catalog_service_key": key,
            "catalog_managed": True,
            "depends_on": list(spec.get("depends_on") or []),
            "required": bool(spec.get("required", True)),
            "start_command": (
                shlex.join([str(x) for x in (spec.get("command") or [])])
                if isinstance(spec.get("command"), (list, tuple)) and spec.get("command")
                else (str(spec.get("command")) if spec.get("command") else None)
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
            "public_host": resolved_config.get("domain") if public else None,
            "healthcheck": healthcheck,
            "healthcheck_path": spec.get("healthcheck_path"),
            "healthcheck_timeout": float(spec.get("healthcheck_timeout") or 5),
        }
        service.runtime_config = runtime_config
        service.build_config = {
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
                    "hostname": str(resolved_config.get("domain") or "") if public else "",
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
            ok, msg = service.can_allocate_storage(size_mb)
            if not ok:
                raise CatalogValidationError(
                    f"Persistent volume {bind!r} for service {key!r} exceeds the service plan storage quota: {msg}"
                )
            vol_name = f"cat-{service.id.hex[:8]}-{safe_slug(str(volume_spec.get('source') or bind))}"[:32]
            volume, _ = Volume.objects.get_or_create(
                name=vol_name,
                defaults={
                    "user": user,
                    "service": service,
                    "service_attachments": {
                        str(service.id): {
                            "bind": bind,
                            "mode": str(volume_spec.get("mode") or "rw"),
                        }
                    },
                    "default_bind": bind,
                    "default_mode": str(volume_spec.get("mode") or "rw"),
                    "size_mb": size_mb,
                },
            )
            if volume.service_id is None:
                volume.attach_to_service(service, bind=bind, mode=str(volume_spec.get("mode") or "rw"))

        deploy = Deploy.objects.create(
            name=allocate_deploy_name(service),
            service=service,
            created_by=created_by,
            version=1.0,
            config=cfg,
            zip_file=_write_archive(dockerfile_text, files),
        )
        ApplicationInstanceService.objects.create(
            instance=instance,
            service=service,
            deploy=deploy,
            service_key=key,
            sequence=sequence,
        )
    return instance
