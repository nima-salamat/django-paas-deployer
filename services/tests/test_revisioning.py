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

        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["env"]["DATABASE_URL"], "[REDACTED]")
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
