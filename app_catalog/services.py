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
from services.models import PrivateNetwork, Service
from deploy.models import Deploy
from core.global_settings.config import PlanTypeChoices
from .catalog import ApplicationCatalog, CatalogValidationError, resolve_variant
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
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


def _unique_deploy_name(service: Service) -> str:
    """Generate a deployment name unique within its service."""
    base = str(service.name)[:50].strip("-") or "app"
    from deploy.models import Deploy
    if not Deploy.objects.filter(service=service, name=base).exists():
        return base
    i = 2
    while True:
        suffix = f"-{i}"
        candidate = (base[: 50 - len(suffix)] + suffix).strip("-")
        if not Deploy.objects.filter(service=service, name=candidate).exists():
            return candidate
        i += 1


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
        secret_config=dict(resolved["secrets"]),
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
            k: _render_service_value(str(v), config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts)
            for k, v in (spec.get("environment") or {}).items()
        }
        image = _render_service_value(str(spec.get("image_template") or spec.get("image") or ""), config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts)
        dockerfile = spec.get("dockerfile")
        healthcheck = spec.get("healthcheck") if isinstance(spec.get("healthcheck"), dict) else None
        if dockerfile:
            dockerfile_text = _render_service_value(str(dockerfile), config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts).replace("${config.image_template}", image)
        elif image:
            dockerfile_text = f"FROM {image}\n"
        healthcheck_instruction = _dockerfile_healthcheck(healthcheck)
        if healthcheck_instruction and "HEALTHCHECK" not in dockerfile_text:
            dockerfile_text = dockerfile_text.rstrip() + "\n" + healthcheck_instruction + "\n"
        else:
            raise CatalogValidationError(f"Catalog service {key} must define an image or Dockerfile.")

        files = {
            str(name): _render_service_value(str(content), config=resolved_config, secrets=resolved["secrets"], service_hosts=service_hosts)
            for name, content in (spec.get("files") or {}).items()
        }
        public = bool(spec.get("public", False))
        port = spec.get("port")
        if public and not port:
            ports = spec.get("ports") or []
            if ports:
                first = ports[0]
                if isinstance(first, dict):
                    port = first.get("target") or first.get("published")
                elif isinstance(first, int):
                    port = first
                else:
                    text = str(first)
                    port = int(text.split(":")[-1].split("/")[0])
        cfg.update({
            "dockerfile_source": "archive",
            "env": env,
            "port": int(port) if public and port else None,
            "healthcheck": healthcheck,
            "healthcheck_path": spec.get("healthcheck_path"),
            "healthcheck_timeout": float(spec.get("healthcheck_timeout") or 5),
            "public": public,
            "public_host": resolved_config.get("domain") if public else None,
            "start_command": shlex.join([str(x) for x in (spec.get("command") or [])]) if isinstance(spec.get("command"), (list, tuple)) and spec.get("command") else (str(spec.get("command")) if spec.get("command") else None),
            "entry_point": shlex.join([str(x) for x in (spec.get("entrypoint") or [])]) if isinstance(spec.get("entrypoint"), (list, tuple)) and spec.get("entrypoint") else (str(spec.get("entrypoint")) if spec.get("entrypoint") else None),
            "restart_policy": dict(spec.get("restart_policy") or {}),
            "working_directory": spec.get("working_directory"),
            "volumes": [
                {
                    "source": f"{slug}-{safe_slug(str(v.get('source') or v.get('name') or key))}",
                    "target": str(v["target"]),
                    "mode": str(v.get("mode") or "rw"),
                    "mount_type": "volume",
                    "size_mb": _render_volume_size(v.get("size_mb"), config=resolved_config, secrets=resolved["secrets"]),
                    "persistent": bool(v.get("persistent", True)),
                }
                for v in (spec.get("volumes") or [])
            ],
        })
        deploy = Deploy.objects.create(
            name=_unique_deploy_name(service),
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
