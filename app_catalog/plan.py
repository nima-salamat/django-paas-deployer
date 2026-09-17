from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ApplicationPlanError(ValueError):
    pass


@dataclass(frozen=True)
class VolumePlan:
    source: str
    target: str
    mode: str = "rw"
    mount_type: str = "volume"
    size_mb: int | None = None


@dataclass(frozen=True)
class ServicePlan:
    key: str
    role: str
    platform: str = "docker"
    plan_type: str = "APP"
    dependencies: tuple[str, ...] = ()
    image: str | None = None
    dockerfile: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    ports: tuple[dict[str, Any], ...] = ()
    volumes: tuple[VolumePlan, ...] = ()
    command: tuple[str, ...] = ()
    entrypoint: tuple[str, ...] = ()
    restart_policy: dict[str, Any] = field(default_factory=dict)
    healthcheck: dict[str, Any] | None = None
    public: bool = False
    labels: dict[str, str] = field(default_factory=dict)
    required: bool = True
    networks: tuple[str, ...] = ()
    working_directory: str | None = None

    @property
    def build_kind(self) -> str:
        if self.dockerfile:
            return "dockerfile"
        if self.image:
            return "image"
        return "none"


@dataclass(frozen=True)
class ApplicationPlan:
    id: str
    version: str
    variant: str
    services: tuple[ServicePlan, ...]
    networks: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def service(self, key: str) -> ServicePlan:
        for svc in self.services:
            if svc.key == key:
                return svc
        raise KeyError(key)

    def topological_order(self) -> tuple[str, ...]:
        pending = {svc.key: set(svc.dependencies) for svc in self.services}
        order: list[str] = []
        while pending:
            ready = sorted(key for key, deps in pending.items() if not deps)
            if not ready:
                raise ApplicationPlanError("Application service dependency graph contains a cycle.")
            for key in ready:
                order.append(key)
                pending.pop(key)
                for deps in pending.values():
                    deps.discard(key)
        return tuple(order)

def ready_service_keys(
    plan: ApplicationPlan,
    statuses: dict[str, str],
    dispatched: set[str] | None = None,
) -> tuple[str, ...]:
    """Return all services whose dependencies are already successful.

    The function is deliberately pure so dependency scheduling can be tested
    without Django/Celery/Docker. Independent services are returned together.
    """
    dispatched = set(dispatched or ())
    ready: list[str] = []
    for service in plan.services:
        if service.key in dispatched or statuses.get(service.key) != "pending":
            continue
        if all(statuses.get(dep) == "succeeded" for dep in service.dependencies):
            ready.append(service.key)
    return tuple(sorted(ready))



def plan_from_resolved(resolved: dict[str, Any]) -> ApplicationPlan:
    services: list[ServicePlan] = []
    for raw in resolved.get("services") or []:
        services.append(
            ServicePlan(
                key=str(raw["key"]),
                role=str(raw.get("role") or "app"),
                platform=str(raw.get("platform") or "docker"),
                plan_type=str(raw.get("plan_type") or "APP"),
                dependencies=tuple(str(x) for x in (raw.get("depends_on") or [])),
                image=raw.get("image_template") or raw.get("image"),
                dockerfile=(raw.get("dockerfile") or None),
                files={str(k): str(v) for k, v in (raw.get("files") or {}).items()},
                environment={str(k): str(v) for k, v in (raw.get("environment") or {}).items()},
                ports=tuple(raw.get("ports") or (({"target": int(raw["port"])} if raw.get("port") else {}),)),
                volumes=tuple(
                    VolumePlan(
                        source=str(v.get("source") or v.get("name") or raw["key"]),
                        target=str(v["target"]),
                        mode=str(v.get("mode") or "rw"),
                        mount_type=str(v.get("mount_type") or "volume"),
                        size_mb=int(v["size_mb"]) if v.get("size_mb") not in (None, "") else None,
                    )
                    for v in (raw.get("volumes") or [])
                ),
                command=tuple(str(x) for x in (raw.get("command") or [])),
                entrypoint=tuple(str(x) for x in (raw.get("entrypoint") or [])) if isinstance(raw.get("entrypoint"), list) else ((str(raw["entrypoint"]),) if raw.get("entrypoint") else ()),
                restart_policy=dict(raw.get("restart_policy") or {}),
                healthcheck=(
                    {
                        "path": raw.get("healthcheck_path"),
                        "timeout": raw.get("healthcheck_timeout"),
                        "expected_status": tuple(raw.get("healthcheck_expected_status") or (200, 204)),
                    }
                    if raw.get("healthcheck_path")
                    else None
                ),
                public=bool(raw.get("public", raw.get("role") == "app" and raw.get("healthcheck_path"))),
                labels={str(k): str(v) for k, v in (raw.get("labels") or {}).items()},
                required=bool(raw.get("required", True)),
                networks=tuple(str(x) for x in (raw.get("networks") or ("default",))),
                working_directory=(str(raw.get("working_directory")) if raw.get("working_directory") else None),
            )
        )
    plan = ApplicationPlan(
        id=str(resolved["catalog_id"]),
        version=str(resolved["definition_version"]),
        variant=str(resolved["variant_id"]),
        services=tuple(services),
        networks=tuple(str(x) for x in (resolved.get("networks") or ())),
        metadata=dict(resolved.get("metadata") or {}),
    )
    plan.topological_order()
    network_sets = [set(svc.networks) for svc in services if svc.networks]
    if network_sets:
        known = set(plan.networks) or {"default"}
        for svc in services:
            if any(net not in known for net in svc.networks):
                raise ApplicationPlanError(f"Service {svc.key!r} references a network that is not declared by the application plan.")
    return plan


def plan_from_compose(compose: dict[str, Any], *, app_id: str, version: str = "1.0.0", variant: str = "default") -> ApplicationPlan:
    """Normalize a supported Compose application into PassDeployer's plan.

    Compose is an input representation here, not the execution engine. The
    adapter intentionally supports the portable service subset used by
    one-click catalogs and rejects host-specific/Swarm-only behavior rather
    than silently changing its meaning.
    """
    if not isinstance(compose, dict) or not isinstance(compose.get("services"), dict):
        raise ApplicationPlanError("Compose definition must contain a services mapping.")
    networks = tuple(str(k) for k in (compose.get("networks") or {}).keys())
    services: list[ServicePlan] = []
    for key, raw in compose["services"].items():
        if not isinstance(raw, dict):
            raise ApplicationPlanError(f"Compose service {key!r} must be an object.")
        unsupported = {"deploy", "network_mode", "privileged"} & set(raw)
        if unsupported:
            raise ApplicationPlanError(
                f"Compose service {key!r} uses unsupported execution features: {', '.join(sorted(unsupported))}."
            )
        build = raw.get("build")
        if isinstance(build, dict) and build.get("dockerfile"):
            dockerfile = str(build["dockerfile"])
        elif isinstance(build, str):
            dockerfile = build
        else:
            dockerfile = None
        env = raw.get("environment") or {}
        if isinstance(env, list):
            env = {str(item).split("=", 1)[0]: str(item).split("=", 1)[1] if "=" in str(item) else "" for item in env}
        ports = []
        for port in raw.get("ports") or []:
            if isinstance(port, int):
                ports.append({"published": port, "target": port})
            else:
                text = str(port)
                host, sep, target = text.partition(":")
                ports.append({"published": int(host) if sep and host.isdigit() else None, "target": int(target if sep else host.split("/")[0])})
        volumes = []
        for vol in raw.get("volumes") or []:
            if isinstance(vol, str):
                source, sep, target = vol.partition(":")
                if not sep:
                    raise ApplicationPlanError(f"Compose volume {vol!r} on {key!r} must specify a target.")
                volumes.append(VolumePlan(source=source, target=target))
            else:
                source = vol.get("source") or vol.get("type") or key
                volumes.append(VolumePlan(source=str(source), target=str(vol["target"]), mode=str(vol.get("read_only") and "ro" or "rw"), mount_type=str(vol.get("type") or "volume")))
        depends = raw.get("depends_on") or {}
        dependencies = tuple(str(x) for x in (depends.keys() if isinstance(depends, dict) else depends))
        health = raw.get("healthcheck")
        service_health = None
        if health:
            service_health = {str(k): v for k, v in health.items()}
        services.append(
            ServicePlan(
                key=str(key),
                role="app",
                platform="docker",
                plan_type="APP",
                dependencies=dependencies,
                image=str(raw.get("image")) if raw.get("image") else None,
                dockerfile=dockerfile,
                environment={str(k): str(v) for k, v in env.items()},
                ports=tuple(ports),
                volumes=tuple(volumes),
                command=tuple(str(x) for x in (raw.get("command") or [])) if isinstance(raw.get("command"), list) else ((str(raw["command"]),) if raw.get("command") else ()),
                entrypoint=tuple(str(x) for x in (raw.get("entrypoint") or [])) if isinstance(raw.get("entrypoint"), list) else ((str(raw["entrypoint"]),) if raw.get("entrypoint") else ()),
                restart_policy={"Name": str(raw.get("restart"))} if raw.get("restart") else {},
                healthcheck=service_health,
                public=bool(raw.get("ports")),
                labels={str(k): str(v) for k, v in (raw.get("labels") or {}).items()},
                required=bool(raw.get("required", True)),
                networks=tuple(str(x) for x in (raw.get("networks") or ("default",))),
                working_directory=(str(raw.get("working_directory")) if raw.get("working_directory") else None),
            )
        )
    plan = ApplicationPlan(id=app_id, version=version, variant=variant, services=tuple(services), networks=networks)
    plan.topological_order()
    return plan
