import os
import tempfile
from pathlib import Path
import unittest

from app_catalog.catalog import ApplicationCatalog, CatalogValidationError, is_public_definition, resolve_variant
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

    def test_deprecated_imported_catalog_is_explicitly_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deprecated.yaml"
            path.write_text(
                "# deprecated: true\n"
                "services:\n"
                "  web:\n"
                "    image: example/web:1\n",
                encoding="utf-8",
            )
            self.assertIsNone(load_yaml_definition(path))

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

    def test_wordpress_official_image_uses_apache_document_root_as_working_dir(self):
        definition = ApplicationCatalog.get("wordpress")
        resolved = resolve_variant(definition, "default", {})
        wordpress = resolved["services"][0]
        self.assertEqual(wordpress["key"], "wordpress")
        self.assertEqual(wordpress["working_directory"], "/var/www/html")
        self.assertEqual(wordpress["volumes"][0]["target"], "/var/www/html")

    def test_wordpress_choice_image_template_is_public(self):
        definition = ApplicationCatalog.get("wordpress")
        self.assertTrue(is_public_definition(definition))

    def test_free_form_image_template_is_not_public(self):
        definition = ApplicationCatalog.get("wordpress")
        data = dict(definition.data)
        variant = dict(next(iter(data["variants"].values())))
        variant["fields"] = [
            field for field in (variant.get("fields") or [])
            if field.get("id") != "software_version"
        ] + [{
            "id": "software_version",
            "label": "WordPress version",
            "type": "string",
            "required": True,
        }]
        variant["services"] = [
            dict(variant["services"][0], image="wordpress:" + "$" + "{config.software_version}" + "-php8.3-apache")
        ]
        data["variants"] = {"default": variant}
        from dataclasses import replace
        self.assertFalse(is_public_definition(replace(definition, data=data)))

    def test_public_catalog_publication_is_model_backed_editorial_state(self):
        source = (Path(__file__).resolve().parents[1] / "models.py").read_text(encoding="utf-8")
        self.assertIn("class CatalogPublication(models.Model):", source)
        self.assertIn('catalog_id = models.CharField(max_length=64, unique=True)', source)
        self.assertIn("featured_override = models.BooleanField(", source)
    def test_wordpress_public_service_uses_ready_marker_healthcheck_and_https_config(self):
        definition = ApplicationCatalog.get("wordpress")
        resolved = resolve_variant(definition, "default", {"domain": "app.example.com"})
        wordpress = next(item for item in resolved["services"] if item["key"] == "wordpress")
        self.assertEqual(wordpress["port"], 80)
        self.assertTrue(wordpress["public"])
        healthcheck = wordpress["healthcheck"]
        self.assertEqual(healthcheck["test"][0], "CMD-SHELL")
        self.assertIn("passdeployer-wordpress-ready", healthcheck["test"][1])
        self.assertIn("wp core is-installed", healthcheck["test"][1])
        self.assertEqual(healthcheck["interval"], "5s")
        self.assertEqual(healthcheck["timeout"], "5s")
        self.assertEqual(healthcheck["start_period"], "15s")
        self.assertEqual(healthcheck["retries"], 24)
        self.assertEqual(
            wordpress["environment"]["WORDPRESS_CONFIG_EXTRA"],
            "define( 'WP_HOME', 'https://app.example.com' );\n"
            "define( 'WP_SITEURL', 'https://app.example.com' );\n"
            "define( 'FORCE_SSL_ADMIN', true );\n"
            "if ( getenv( 'WORDPRESS_MANAGED_CRON' ) === '1' ) { define( 'DISABLE_WP_CRON', true ); }"
        )
        self.assertIn("FROM wordpress:7.1.2-php8.3-apache", wordpress["dockerfile"])
        self.assertIn("ARG WP_CLI_VERSION=2.12.0", wordpress["dockerfile"])
        self.assertIn("mariadb-client", wordpress["dockerfile"])
        self.assertIn("WP_CLI_ALLOW_ROOT=1", wordpress["dockerfile"])
        self.assertIn("wp-cli-${WP_CLI_VERSION}.phar", wordpress["dockerfile"])
        self.assertIn("sha512sum -c -", wordpress["dockerfile"])
        self.assertFalse(wordpress.get("command"))
        self.assertIn("WORDPRESS_ADMIN_USER", wordpress["environment"])
        self.assertIn("WORDPRESS_ADMIN_PASSWORD", wordpress["environment"])
        self.assertIn("WORDPRESS_ADMIN_EMAIL", wordpress["environment"])
        self.assertNotIn("wp_cli_version", {field["id"] for field in resolved["fields"]})

    def test_inline_dockerfile_preserves_native_build_variables(self):
        resolved = compose_to_resolved(
            document={
                "services": {
                    "web": {
                        "x-passdeployer": {
                            "dockerfile": "FROM alpine:3.20\\nARG TOOL_VERSION=1.2.3\\nRUN echo \\"${TOOL_VERSION}\\" > /version",
                        },
                        "image": "example/web:1",
                    }
                }
            },
            metadata={},
            config={},
            secrets={},
            catalog_id="native-dockerfile-vars",
            version="1",
        )
        dockerfile = resolved["services"][0]["dockerfile"]
        self.assertIn("${TOOL_VERSION}", dockerfile)
        self.assertNotIn("tool_version", {field["id"] for field in resolved["fields"]})

    def test_wordpress_version_is_selectable_and_pinned_to_official_tags(self):
        definition = ApplicationCatalog.get("wordpress")
        variant = definition.variants["default"]
        version_field = next(field for field in variant["fields"] if field["id"] == "software_version")
        self.assertEqual(version_field["type"], "choice")
        self.assertEqual(version_field["default"], "7.1.2")
        self.assertEqual(version_field["options"], ["7.1.2", "7.1.1", "7.1.0"])

        resolved = resolve_variant(definition, "default", {"software_version": "7.1.1"})
        wordpress = next(item for item in resolved["services"] if item["key"] == "wordpress")
        self.assertIn("FROM wordpress:7.1.1-php8.3-apache", wordpress["dockerfile"])

    def test_wordpress_rejects_unlisted_version(self):
        definition = ApplicationCatalog.get("wordpress")
        with self.assertRaises(CatalogValidationError):
            resolve_variant(definition, "default", {"software_version": "7.1.3"})

    def test_public_host_placeholder_is_replaced_during_final_service_render(self):
        from app_catalog.services import _PLATFORM_PUBLIC_HOST_TOKEN, _render_service_value

        rendered = _render_service_value(
            "https://" + _PLATFORM_PUBLIC_HOST_TOKEN + "/wp-admin/install.php",
            config={"domain": "app.example.com"},
            secrets={},
            service_hosts={},
        )

        self.assertEqual(
            rendered,
            "https://app.example.com/wp-admin/install.php",
        )
        self.assertNotIn(_PLATFORM_PUBLIC_HOST_TOKEN, rendered)

    def test_external_env_interpolation_is_safe_and_generated(self):
        definition = load_yaml_definition(Path(ApplicationCatalog.get("n8n-with-postgres-and-worker").source))
        self.assertIsNotNone(definition)
        resolved = resolve_variant(definition, "default", {"domain": "n8n.example.com"})
        self.assertTrue(resolved["secrets"])
        self.assertNotIn("${config.", str(resolved["services"]))
        self.assertNotIn("${secret.", str(resolved["services"]))


    def test_wordpress_managed_install_and_scaled_resource_contract(self):
        definition = ApplicationCatalog.get("wordpress")
        resolved = resolve_variant(
            definition,
            "default",
            {
                "php_version": "8.4",
                "wordpress_site_title": "Agent Site",
                "wordpress_admin_user": "agent-admin",
                "wordpress_admin_email": "agent@example.com",
                "wordpress_replicas": 3,
            },
        )
        wordpress = next(item for item in resolved["services"] if item["key"] == "wordpress")
        self.assertEqual(wordpress["replicas"], 3)
        self.assertIn("wp-cli-" + "${WP_CLI_VERSION}.phar", wordpress["dockerfile"])
        self.assertIn("passdeployer-wordpress-entrypoint.sh", wordpress["dockerfile"])
        self.assertIn("wp core install", wordpress["dockerfile"])
        self.assertIn("WORDPRESS_ADMIN_EMAIL", wordpress["environment"])
        self.assertIn("WORDPRESS_TABLE_PREFIX", wordpress["environment"])
        self.assertIn("WORDPRESS_MANAGED_CRON", wordpress["environment"])
        self.assertIn("FROM wordpress:7.1.2-php8.4-apache", wordpress["dockerfile"])

    def test_wordpress_replica_is_preserved_in_application_plan(self):
        definition = ApplicationCatalog.get("wordpress")
        resolved = resolve_variant(definition, "default", {"wordpress_replicas": 2})
        plan = plan_from_resolved(resolved)
        wordpress = plan.service("wordpress")
        self.assertEqual(wordpress.replicas, 2)


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



def test_imported_database_compose_service_is_normalized_as_db_service():
    from app_catalog.compose_catalog import compose_to_resolved
    resolved = compose_to_resolved(
        document={
            "services": {
                "postgres": {
                    "image": "postgres:16-alpine",
                    "environment": [
                        "POSTGRES_USER=app",
                        "POSTGRES_DB=app",
                        "POSTGRES_PASSWORD=$SERVICE_PASSWORD_POSTGRES",
                    ],
                },
                "web": {"image": "example/web:1", "depends_on": ["postgres"]},
            }
        },
        metadata={}, config={},
        secrets={"service_password_postgres": "fixed-secret"},
        catalog_id="compose-db", version="1",
    )
    db = next(item for item in resolved["services"] if item["key"] == "postgres")
    assert db["role"] == "database"
    assert db["platform"] == "postgresql"
    assert db["plan_type"] == "DB"
    assert db["environment"]["POSTGRES_PASSWORD"] == "${" + "secret.service_password_postgres}"
