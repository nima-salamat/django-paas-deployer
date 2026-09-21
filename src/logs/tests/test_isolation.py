from django.test import SimpleTestCase
from pathlib import Path


class LoggingIsolationTests(SimpleTestCase):
    def test_consumer_has_no_docker_follow(self):
        body = Path("services/consumers.py").read_text()
        # ServiceLogsConsumer must not call docker follow
        # Allow RestrictedShell and other classes; check the ServiceLogsConsumer section
        start = body.find("class ServiceLogsConsumer")
        end = body.find("\nclass ", start + 10)
        section = body[start:end if end > 0 else None]
        self.assertNotIn("follow=True", section)
        self.assertNotIn("stream_container_logs", section)
        self.assertNotIn("containers.get", section)

    def test_runtime_api_no_docker_fallback(self):
        body = Path("services/api/runtime.py").read_text()
        start = body.find("def service_logs_apiview")
        end = body.find("\ndef ", start + 10)
        section = body[start:end]
        self.assertNotIn("docker_fallback", section)
        self.assertNotIn("containers.get", section)

    def test_celery_tasks_are_maintenance_only(self):
        body = Path("logs/tasks.py").read_text()
        self.assertNotIn("container.logs", body)
        self.assertNotIn("follow=True", body)
