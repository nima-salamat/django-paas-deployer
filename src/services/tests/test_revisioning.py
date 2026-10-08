import os

import pytest

if os.environ.get("DJANGO_FULL_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("requires the full Django application registry", allow_module_level=True)
pytestmark = pytest.mark.deployment_integration

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.revisioning import (
    redact_config,
    _catalog_revision_requires_refresh,
    _normalize_process_specs,
)


class RevisioningContractTests(SimpleTestCase):
    def test_redact_config_marks_nested_secret_keys_without_mutating_input(self):
        source = {
            "env": {"DATABASE_URL": "postgres://secret", "PUBLIC": "ok"},
            "password": "top-secret",
        }

        redacted, keys = redact_config(source)

        self.assertEqual(redacted["password"], "[SECRET_REF]")
        self.assertEqual(redacted["env"]["DATABASE_URL"], "[SECRET_REF]")
        self.assertEqual(redacted["env"]["PUBLIC"], "ok")
        self.assertIn("password", keys)
        self.assertIn("env.DATABASE_URL", keys)
        self.assertEqual(source["password"], "top-secret")

    def test_catalog_revision_refreshes_when_existing_file_content_is_stale(self):
        service = SimpleNamespace(
            source_kind="catalog",
            build_config={"files": {"passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\\necho new\\n"}},
        )
        revision = SimpleNamespace(
            config_snapshot={"source_kind": "catalog"},
            build_snapshot={"files": {"passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\\necho old\\n"}},
        )

        self.assertTrue(_catalog_revision_requires_refresh(service, revision))

    def test_catalog_revision_does_not_refresh_identical_build_files(self):
        files = {"passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\\necho same\\n"}
        service = SimpleNamespace(source_kind="catalog", build_config={"files": files})
        revision = SimpleNamespace(
            config_snapshot={"source_kind": "catalog"},
            build_snapshot={"files": dict(files)},
        )

        self.assertFalse(_catalog_revision_requires_refresh(service, revision))

    def test_catalog_revision_refreshes_when_dockerfile_is_stale(self):
        current = (
            "FROM wordpress:7.1.2-php8.4-apache\\n"
            'ENTRYPOINT ["/usr/local/bin/docker-ensure-installed.sh"]\\n'
            'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\\n'
        )
        stale = (
            "FROM wordpress:7.1.2-php8.4-apache\\n"
            'ENTRYPOINT ["docker-entrypoint.sh"]\\n'
            'CMD ["apache2-foreground"]\\n'
        )
        files = {"passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\\nset -eu\\n"}
        service = SimpleNamespace(
            source_kind="catalog",
            build_config={"dockerfile": current, "files": files},
        )
        revision = SimpleNamespace(
            config_snapshot={"source_kind": "catalog"},
            build_snapshot={"dockerfile": stale, "files": dict(files)},
        )

        self.assertTrue(_catalog_revision_requires_refresh(service, revision))

    @patch("services.revisioning.ServiceProcess.objects")
    def test_legacy_config_derives_web_and_celery_processes(self, objects):
        objects.filter.return_value.order_by.return_value = []

        service = SimpleNamespace()
        config = {
            "start_command": "gunicorn app.wsgi",
            "worker_count": 2,
            "celery": True,
            "celery_beat": True,
        }

        specs = _normalize_process_specs(service, config)

        self.assertEqual([item["name"] for item in specs], ["web", "worker", "scheduler"])
        self.assertEqual(specs[0]["command"], "gunicorn app.wsgi")
        self.assertEqual(specs[1]["replicas"], 2)
        self.assertEqual(specs[2]["process_type"], "scheduler")


class RuntimeGraphContractTests(SimpleTestCase):
    def test_environment_scope_is_preserved(self):
        from deployments.core.runtime_graph import ServiceRuntimeGraph

        revision = SimpleNamespace(
            pk="revision-id",
            revision_number=3,
            source_snapshot={},
            build_snapshot={},
            runtime_snapshot={},
            environment_snapshot={
                "BUILD_ONLY": {"value": "build", "scope": "build"},
                "RUNTIME_ONLY": {"value": "runtime", "scope": "runtime"},
                "BOTH": {"value": "both", "scope": "both"},
            },
            process_snapshot=[
                {"name": "web", "process_type": "web", "replicas": 1, "enabled": True}
            ],
            endpoint_snapshot=[
                {
                    "name": "http",
                    "target_port": 8080,
                    "published_port": None,
                    "protocol": "http",
                    "exposure": "public",
                    "hostname": "app.example.com",
                    "path": "",
                    "tls": False,
                    "enabled": True,
                }
            ],
            volume_snapshot=[],
            network_snapshot=[],
        )

        graph = ServiceRuntimeGraph.from_revision(revision)

        self.assertEqual(graph.build_environment["BUILD_ONLY"], "build")
        self.assertEqual(graph.runtime_environment["RUNTIME_ONLY"], "runtime")
        self.assertEqual(graph.runtime_environment["BOTH"], "both")
        self.assertNotIn("BUILD_ONLY", graph.runtime_environment)
        self.assertNotIn("RUNTIME_ONLY", graph.build_environment)
        self.assertEqual(graph.exposed_ports(), {"8080/tcp": {}})
