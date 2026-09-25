#!/usr/bin/env python
"""Run a real Ready-to-Deploy application deployment through Celery/Docker.

Usage (from the integration-test container or project environment):
    python scripts/run_ready_app_integration.py --app mattermost --timeout 900

The command intentionally uses the normal Django ORM and Celery broker. It does
not call docker compose to deploy the application under test.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import docker

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from app_catalog.apis import ApplicationInstanceListCreateAPIView  # noqa: E402,F401
from app_catalog.catalog import ApplicationCatalog, resolve_variant  # noqa: E402
from app_catalog.services import create_application_installation  # noqa: E402
from app_catalog.tasks import start_application_installation  # noqa: E402
from app_catalog.models import ApplicationInstance, ApplicationStatus  # noqa: E402
from plans.models import Plan  # noqa: E402
from users.models import User  # noqa: E402
from core.global_settings.config import PlanTypeChoices, StorageTypeChoices  # noqa: E402


def ensure_plans() -> tuple[Plan, Plan]:
    common = {
        "max_cpu": 2.0,
        "max_ram": 4096,
        "max_storage": 20,
        "price_per_hour": 0,
        "storage_type": StorageTypeChoices.SSD,
    }
    app, _ = Plan.objects.get_or_create(
        name="Bronze", platform="docker", plan_type=PlanTypeChoices.APP,
        defaults=common,
    )
    db, _ = Plan.objects.get_or_create(
        name="Bronze", platform="postgresql", plan_type=PlanTypeChoices.DB,
        defaults=common,
    )
    return app, db


def wait(instance_id: str, timeout: int) -> ApplicationInstance:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance = ApplicationInstance.objects.prefetch_related("services__deploy").get(pk=instance_id)
        print(f"application={instance.id} status={instance.status} stage={instance.stage}")
        if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
            return instance
        time.sleep(3)
    raise TimeoutError(f"Application {instance_id} did not reach a terminal state within {timeout}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=["mattermost", "synapse"], default="mattermost")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    user, _ = User.objects.get_or_create(
        username="integration-test",
        defaults={"email": "integration-test@example.invalid", "is_active": True},
    )
    app_plan, _db_plan = ensure_plans()

    catalog_id = args.app
    domain = args.domain or f"{args.app}.integration.test"
    config = {"domain": domain}
    if args.app == "mattermost":
        config["storage_mb"] = 4096
    else:
        config["report_stats"] = "no"

    definition = ApplicationCatalog.get(catalog_id)
    resolved = resolve_variant(definition, "postgresql", config)
    print(f"resolved plan services={[s['key'] for s in resolved['services']]}")

    existing = ApplicationInstance.objects.filter(user=user, slug=args.app).first()
    if existing and existing.status in {ApplicationStatus.DEPLOYING, ApplicationStatus.RUNNING}:
        raise RuntimeError(f"Integration application {args.app!r} already exists in {existing.status} state.")
    if existing:
        existing.delete()

    instance = create_application_installation(
        user,
        {
            "catalog_id": catalog_id,
            "variant": "postgresql",
            "name": args.app,
            "plan_id": app_plan.pk,
            "config": config,
        },
    )
    print(f"created application instance {instance.pk}")
    start_application_installation.delay(str(instance.pk))

    final = wait(str(instance.pk), args.timeout)
    print(f"FINAL status={final.status} stage={final.stage} error_code={final.error_code}")
    for binding in final.services.select_related("deploy", "service"):
        print(
            f"SERVICE {binding.service_key} status={binding.deploy.status} "
            f"stage={binding.deploy.stage} service={binding.service.name} deploy={binding.deploy.pk}"
        )

    if final.status != ApplicationStatus.RUNNING:
        return 1

    client = docker.from_env()
    containers = client.containers.list(all=True, filters={"label": [f"application.id={final.pk}"]})
    if len(containers) != len(final.services.all()):
        raise RuntimeError(
            f"Expected {final.services.count()} application-owned containers, found {len(containers)}"
        )

    expected_network = next(iter(final.services.select_related("service__network"))).service.network.get_docker_network_name()
    public_keys = {
        "mattermost",
        "synapse",
    }
    for container in containers:
        labels = container.labels or {}
        if labels.get("application.id") != str(final.pk):
            raise RuntimeError(f"Container {container.name} has incorrect application ownership label")
        networks = set((container.attrs.get("NetworkSettings") or {}).get("Networks") or {})
        if expected_network not in networks:
            raise RuntimeError(f"Container {container.name} is not attached to application network {expected_network}")
        key = labels.get("application.service")
        if key not in public_keys and any(k.startswith("traefik.http.routers.") for k in labels):
            raise RuntimeError(f"Internal service {key} unexpectedly has public Traefik routing labels")

    print(f"DOCKER CHECK: {len(containers)} owned containers share {expected_network}; public routing is limited to the application service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
