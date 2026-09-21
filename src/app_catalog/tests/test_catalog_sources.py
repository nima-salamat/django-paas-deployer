import os
import tempfile
from pathlib import Path
import unittest

from app_catalog.catalog import ApplicationCatalog, CatalogValidationError, resolve_variant
from app_catalog.compose import load_compose
from app_catalog.compose_catalog import compose_to_resolved
from app_catalog.plan import ApplicationPlanError, plan_from_resolved
from app_catalog.source_loader import load_yaml_definition


class CatalogSourceTests(unittest.TestCase):
    def test_representative_catalog_is_generic(self):
        expected = {
            "uptime-kuma",
            "docmost",
            "n8n-with-postgres-and-worker",
            "mattermost",
            "matrix-synapse-with-postgresql",
            "grafana-with-postgresql",
            "nextcloud-with-postgres",
            "wordpress-with-mariadb",
        }
        self.assertTrue(expected.issubset({item.id for item in ApplicationCatalog.definitions()}))

    def test_realistic_multi_service_plans(self):
        cases = {
            "docmost": ("default", {"domain": "docs.example.com", "mail_driver": "test"}),
            "n8n-with-postgres-and-worker": ("default", {"domain": "n8n.example.com"}),
            "matrix-synapse-with-postgresql": ("default", {"domain": "matrix.example.com", "synapse_server_name": "example.com"}),
        }
        for catalog_id, (variant, values) in cases.items():
            definition = ApplicationCatalog.get(catalog_id)
            resolved = resolve_variant(definition, variant, values)
            plan = plan_from_resolved(resolved)
            self.assertEqual(len(plan.topological_order()), len(plan.services))
            public = [svc.key for svc in plan.services if svc.public]
            self.assertEqual(len(public), 1, catalog_id)
            self.assertTrue(any(svc.role == "database" for svc in plan.services), catalog_id)

    def test_external_catalog_directory_is_loaded(self):
        compose = """
services:
  web:
    image: example/web:1
    ports: [8080]
    environment:
      APP_SECRET: ${APP_SECRET}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.yaml"
            path.write_text("# category: demo\n# slogan: Example\n" + compose, encoding="utf-8")
            old = os.environ.get("APP_CATALOG_SOURCE_DIRS")
            os.environ["APP_CATALOG_SOURCE_DIRS"] = tmp
            try:
                definition = load_yaml_definition(path)
                self.assertEqual(definition.id, "example")
                resolved = resolve_variant(definition, "default", {"app_secret": "safe"})
                self.assertEqual(plan_from_resolved(resolved).service("web").image, "example/web:1")
            finally:
                if old is None:
                    os.environ.pop("APP_CATALOG_SOURCE_DIRS", None)
                else:
                    os.environ["APP_CATALOG_SOURCE_DIRS"] = old

    def test_unsafe_compose_is_rejected(self):
        with self.assertRaises(CatalogValidationError):
            load_compose("""
services:
  web:
    image: example/web:1
    privileged: true
""", app_id="unsafe")

    def test_custom_network_is_rejected(self):
        with self.assertRaises(CatalogValidationError):
            load_compose("""
services:
  web:
    image: example/web:1
    networks: [hostish]
networks:
  hostish: {}
""", app_id="unsafe-network")

    def test_hardcoded_sensitive_value_is_rejected(self):
        with self.assertRaises(ApplicationPlanError):
            compose_to_resolved(
                document={
                    "services": {
                        "db": {
                            "image": "postgres:16",
                            "environment": {"POSTGRES_PASSWORD": "super-secret"},
                        }
                    }
                },
                metadata={},
                config={},
                secrets={},
                catalog_id="unsafe-secret",
                version="1",
            )

    def test_external_env_interpolation_is_safe_and_generated(self):
        definition = load_yaml_definition(Path(ApplicationCatalog.get("n8n-with-postgres-and-worker").source))
        self.assertIsNotNone(definition)
        resolved = resolve_variant(definition, "default", {"domain": "n8n.example.com"})
        self.assertTrue(resolved["secrets"])
        self.assertNotIn("${config.", str(resolved["services"]))
        self.assertNotIn("${secret.", str(resolved["services"]))


if __name__ == "__main__":
    unittest.main()

class CoolifyStyleImportTests(unittest.TestCase):
    def test_coolify_style_service_urls_mark_only_matching_services_public(self):
        compose = """
services:
  api:
    image: example/api:1
    environment:
      - SERVICE_URL_API_8080
    expose: [8080]
  worker:
    image: example/worker:1
    environment:
      - SERVICE_URL_API_8080
    command: worker
  metrics:
    image: example/metrics:1
    environment:
      - SERVICE_URL_METRICS_9090
    expose: [9090]
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coolify-style.yaml"
            path.write_text("# category: demo\n" + compose, encoding="utf-8")
            definition = load_yaml_definition(path)
            resolved = resolve_variant(definition, "default", {"domain": "apps.example.com"})
            public = {svc["key"] for svc in resolved["services"] if svc["public"]}
            self.assertEqual(public, {"api", "metrics"})
            self.assertNotIn("worker", public)

    def test_safe_restart_policy_is_imported_and_unsafe_runtime_features_rejected(self):
        definition = load_yaml_definition(Path(tempfile.mkdtemp()) / "placeholder.yaml") if False else None
        plan = load_compose("""
services:
  init:
    image: example/init:1
    entrypoint: ["/bin/sh", "-c"]
    restart: "no"
""", app_id="restart-policy")
        self.assertEqual(plan.service("init").restart_policy["Name"], "no")
        self.assertEqual(plan.service("init").entrypoint, ("/bin/sh", "-c"))
        for key, value in (("container_name", "fixed"), ("network_mode", "host")):
            with self.subTest(key=key):
                with self.assertRaises(CatalogValidationError):
                    load_compose(f"""
services:
  web:
    image: example/web:1
    {key}: {value}
""", app_id="unsupported")
