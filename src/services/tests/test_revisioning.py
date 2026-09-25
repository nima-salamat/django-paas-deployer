import os

import pytest

if os.environ.get("DJANGO_FULL_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("requires the full Django application registry", allow_module_level=True)
pytestmark = pytest.mark.deployment_integration

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.revisioning import redact_config, _normalize_process_specs


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
