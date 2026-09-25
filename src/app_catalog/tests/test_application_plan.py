from app_catalog.catalog import (
    ApplicationCatalog,
    CatalogDefinition,
    CatalogValidationError,
    resolve_variant,
)
from app_catalog.compose import load_compose
from app_catalog.plan import plan_from_resolved, ApplicationPlanError


def _resolved(services, *, app_id="fixture", variant="default"):
    return {
        "catalog_id": app_id,
        "definition_version": "1.0.0",
        "variant_id": variant,
        "config": {},
        "secrets": {},
        "services": services,
    }


def test_normalized_plan_supports_single_service():
    plan = plan_from_resolved(_resolved([{
        "key": "web", "role": "app", "platform": "docker",
        "image_template": "example/web:1.2", "port": 8080,
    }]))
    assert plan.topological_order() == ("web",)
    assert plan.service("web").build_kind == "image"


def test_normalized_plan_supports_web_database():
    plan = plan_from_resolved(_resolved([
        {"key": "db", "role": "database", "platform": "postgresql", "port": 5432},
        {"key": "web", "role": "app", "platform": "docker", "image_template": "example/web:1", "port": 8080, "depends_on": ["db"]},
    ]))
    assert plan.topological_order() == ("db", "web")
    assert plan.service("web").dependencies == ("db",)


def test_normalized_plan_supports_web_database_redis_worker():
    plan = plan_from_resolved(_resolved([
        {"key": "db", "role": "database", "platform": "postgresql", "port": 5432},
        {"key": "redis", "role": "cache", "platform": "docker", "image_template": "redis:7", "port": 6379},
        {"key": "web", "role": "app", "platform": "docker", "image_template": "example/web:2", "port": 8080, "depends_on": ["db", "redis"]},
        {"key": "worker", "role": "worker", "platform": "docker", "image_template": "example/web:2", "depends_on": ["db", "redis"]},
    ]))
    assert plan.topological_order() == ("db", "redis", "web", "worker")
    assert plan.service("worker").role == "worker"


def test_compose_is_normalized_into_same_internal_plan():
    compose = """
services:
  db:
    image: postgres:17
  redis:
    image: redis:7
  web:
    image: example/web:1
    ports:
      - "8080:8080"
    depends_on:
      - db
      - redis
"""
    plan = load_compose(compose, app_id="compose-fixture")
    assert plan.topological_order() == ("db", "redis", "web")
    assert plan.service("web").image == "example/web:1"
    assert plan.service("web").ports[0]["target"] == 8080


def test_compose_rejects_unsupported_execution_semantics_instead_of_silently_changing_them():
    compose = """
services:
  web:
    image: example/web:1
    deploy:
      replicas: 2
"""
    try:
        load_compose(compose, app_id="bad")
    except CatalogValidationError as exc:
        assert "unsupported execution features" in str(exc)
    else:
        raise AssertionError("unsupported Compose semantics were accepted")


def test_ready_service_keys_returns_all_independent_roots():
    from app_catalog.plan import ready_service_keys
    plan = plan_from_resolved(_resolved([
        {"key": "db", "role": "database", "platform": "postgresql"},
        {"key": "redis", "role": "cache", "platform": "docker", "image_template": "redis:7"},
        {"key": "web", "role": "app", "platform": "docker", "image_template": "example/web:1", "depends_on": ["db", "redis"]},
    ]))
    statuses = {"db": "pending", "redis": "pending", "web": "pending"}
    assert ready_service_keys(plan, statuses) == ("db", "redis")


def test_ready_service_keys_releases_dependents_only_after_all_dependencies_succeed():
    from app_catalog.plan import ready_service_keys
    plan = plan_from_resolved(_resolved([
        {"key": "db", "role": "database", "platform": "postgresql"},
        {"key": "redis", "role": "cache", "platform": "docker", "image_template": "redis:7"},
        {"key": "web", "role": "app", "platform": "docker", "image_template": "example/web:1", "depends_on": ["db", "redis"]},
        {"key": "worker", "role": "worker", "platform": "docker", "image_template": "example/web:1", "depends_on": ["db", "redis"]},
    ]))
    statuses = {"db": "succeeded", "redis": "pending", "web": "pending", "worker": "pending"}
    assert ready_service_keys(plan, statuses) == ("redis",)
    statuses["redis"] = "succeeded"
    assert ready_service_keys(plan, statuses) == ("web", "worker")


def test_real_catalog_applications_resolve_into_executable_plans():
    from app_catalog.catalog import ApplicationCatalog, resolve_variant

    for app_id, variant_id, config in [
        ("synapse", "postgresql", {"domain": "synapse.example.test"}),
        ("mattermost", "postgresql", {"domain": "mattermost.example.test", "storage_mb": 4096}),
    ]:
        definition = ApplicationCatalog.get(app_id)
        resolved = resolve_variant(definition, variant_id, config)
        plan = plan_from_resolved(resolved)
        assert plan.services
        assert plan.topological_order()[0] == "postgres"
        app = plan.service(variant_id.split("+")[0]) if False else None

    mattermost = plan_from_resolved(
        resolve_variant(
            ApplicationCatalog.get("mattermost"),
            "postgresql",
            {"domain": "mattermost.example.test", "storage_mb": 4096},
        )
    )
    assert mattermost.service("mattermost").volumes[0].size_mb == 4096
