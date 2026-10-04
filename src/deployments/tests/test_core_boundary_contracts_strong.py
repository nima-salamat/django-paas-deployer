"""Strong execution-adjacent deployment contract tests.

These tests deliberately target pure decision boundaries and mocked runtime
edges so the normal CI suite remains deterministic and Docker-daemon free.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import DeploymentSecurityError, DeploymentValidationError, HealthCheckError, VolumeError
from deployments.core.types import DeploymentConfig, EndpointSpec, NetworkSpec, VolumeSpec


class HealthCheckerContracts(unittest.TestCase):
    def test_normalize_path_accepts_relative_and_absolute_paths(self):
        from deployments.core.health import DockerHealthChecker

        self.assertIsNone(DockerHealthChecker._normalize_path(None))
        self.assertIsNone(DockerHealthChecker._normalize_path("  "))
        self.assertEqual(DockerHealthChecker._normalize_path("health"), "/health")
        self.assertEqual(DockerHealthChecker._normalize_path("/ready"), "/ready")

    def test_container_port_prefers_internal_exposed_port_not_host_port(self):
        from deployments.core.health import DockerHealthChecker

        info = {
            "Config": {"ExposedPorts": {"8080/tcp": {}}},
            "NetworkSettings": {
                "Ports": {"8080/tcp": [{"HostPort": "443"}]},
            },
        }
        self.assertEqual(DockerHealthChecker._container_port(info), 8080)

    def test_container_ip_uses_first_network_address(self):
        from deployments.core.health import DockerHealthChecker

        info = {
            "NetworkSettings": {
                "Networks": {
                    "proxy": {"IPAddress": "10.0.0.10"},
                    "other": {"IPAddress": "10.0.0.11"},
                }
            }
        }
        self.assertEqual(DockerHealthChecker._container_ip(info), "10.0.0.10")

    def test_readiness_probe_accepts_expected_status(self):
        from deployments.core.health import DockerHealthChecker

        response = MagicMock()
        response.status = 204
        response.__enter__.return_value = response
        with patch("deployments.core.health.urllib.request.urlopen", return_value=response):
            result = DockerHealthChecker()._probe_http(
                {"NetworkSettings": {"Networks": {"proxy": {"IPAddress": "10.0.0.10"}}}},
                container_name="web",
                path="/health",
                port=8000,
                expected_status=(200, 204),
                timeout=1.0,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["http_status"], 204)
        self.assertIsNone(result["failure_type"])

    def test_readiness_probe_reports_unexpected_http_status(self):
        from deployments.core.health import DockerHealthChecker
        from urllib.error import HTTPError

        error = HTTPError("http://10.0.0.10:8000/health", 503, "down", {}, None)
        with patch("deployments.core.health.urllib.request.urlopen", side_effect=error):
            result = DockerHealthChecker()._probe_http(
                {"NetworkSettings": {"Networks": {"proxy": {"IPAddress": "10.0.0.10"}}}},
                container_name="web",
                path="/health",
                port=8000,
                expected_status=(200,),
                timeout=1.0,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["http_status"], 503)
        self.assertEqual(result["failure_type"], "http_status")

    def test_readiness_probe_requires_container_ip(self):
        from deployments.core.health import DockerHealthChecker

        result = DockerHealthChecker()._probe_http(
            {"NetworkSettings": {"Networks": {}}},
            container_name="web",
            path="/health",
            port=8000,
            expected_status=(200,),
            timeout=1.0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_type"], "no_container_ip")

    def test_wait_until_healthy_requires_consecutive_running_polls(self):
        from deployments.core import health as health_module

        class FakeContainer:
            def __init__(self, name):
                self.name = name

            def status(self):
                return "running"

            def inspect(self):
                return {"State": {}}

        checker = health_module.DockerHealthChecker(min_running_polls=3)
        with patch.object(health_module, "Container", FakeContainer),              patch.object(health_module.time, "monotonic", side_effect=[0.0, 0.0, 0.0, 0.0]),              patch.object(health_module.time, "sleep"):
            result = checker.wait_until_healthy(
                "web",
                timeout=10,
                interval=0,
                allow_running_without_healthcheck=True,
            )
        self.assertTrue(result["ready"])
        self.assertEqual(result["consecutive_polls"], 3)
        self.assertFalse(result["docker_healthcheck"])

    def test_wait_until_healthy_honors_cancellation_before_container_access(self):
        from deployments.core.health import DockerHealthChecker

        with patch("deployments.core.health.Container") as container:
            with self.assertRaises(Exception) as ctx:
                DockerHealthChecker().wait_until_healthy(
                    "web",
                    timeout=10,
                    cancel_check=lambda: True,
                )
        self.assertEqual(ctx.exception.stage, "cancelled")
        container.assert_not_called()

    def test_unhealthy_container_raises_structured_health_error(self):
        from deployments.core import health as health_module

        class FakeContainer:
            def __init__(self, name):
                self.name = name

            def status(self):
                return "unhealthy"

            def inspect(self):
                return {"State": {"Health": {"Status": "unhealthy"}}}

        checker = health_module.DockerHealthChecker(min_running_polls=2)
        with patch.object(health_module, "Container", FakeContainer):
            with self.assertRaises(HealthCheckError) as ctx:
                checker.wait_until_healthy("web", timeout=1, interval=0)
        self.assertEqual(ctx.exception.code, "HEALTH_CHECK_FAILED")
        self.assertEqual(ctx.exception.stage, "health_check")


class RoutingContracts(unittest.TestCase):
    def test_explicit_endpoint_hostname_wins(self):
        from deployments.core import routing

        config = SimpleNamespace(name="my-app", public_host="config.example.test")
        endpoint = SimpleNamespace(hostname="Custom.Example.Test.")
        with patch.object(routing, "settings", SimpleNamespace(DEPLOYMENT_DOMAIN="apps.example.test")):
            self.assertEqual(routing.resolve_public_host(config, endpoint), "custom.example.test")

    def test_config_public_host_wins_when_endpoint_has_no_hostname(self):
        from deployments.core import routing

        config = SimpleNamespace(name="my-app", public_host="Config.Example.Test.")
        endpoint = SimpleNamespace(hostname="")
        with patch.object(routing, "settings", SimpleNamespace(DEPLOYMENT_DOMAIN="apps.example.test")):
            self.assertEqual(routing.resolve_public_host(config, endpoint), "config.example.test")

    def test_service_name_and_deployment_domain_form_default_host(self):
        from deployments.core import routing

        config = SimpleNamespace(name="My-App.", public_host="")
        endpoint = SimpleNamespace(hostname="")
        with patch.object(routing, "settings", SimpleNamespace(DEPLOYMENT_DOMAIN="Apps.Example.Test.")):
            self.assertEqual(routing.resolve_public_host(config, endpoint), "my-app.apps.example.test")

    def test_public_http_endpoints_filter_disabled_private_and_non_http_protocols(self):
        from deployments.core import routing

        valid = EndpointSpec(name="web", target_port=8000, protocol="http", exposure="public", enabled=True)
        private = EndpointSpec(name="private", target_port=9000, protocol="http", exposure="internal", enabled=True)
        disabled = EndpointSpec(name="disabled", target_port=7000, protocol="http", exposure="public", enabled=False)
        tcp = EndpointSpec(name="tcp", target_port=6000, protocol="tcp", exposure="public", enabled=True)
        config = SimpleNamespace(endpoints=[valid, private, disabled, tcp], port=8000, platform_type="app", labels={"process.name":"web"})
        result = routing.public_http_endpoints(config)
        self.assertEqual(result, [valid])

    def test_legacy_public_port_is_preserved_for_web_app_without_endpoint_rows(self):
        from deployments.core import routing

        config = SimpleNamespace(
            endpoints=[],
            port=8080,
            platform_type="application",
            labels={"process.name": "web"},
        )
        result = routing.public_http_endpoints(config)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].target_port, 8080)
        self.assertEqual(result[0].exposure, "public")

    def test_legacy_public_port_is_not_created_for_worker_or_database(self):
        from deployments.core import routing

        for process_name, platform_type in (("worker", "app"), ("web", "db")):
            with self.subTest(process_name=process_name, platform_type=platform_type):
                config = SimpleNamespace(
                    endpoints=[],
                    port=8080,
                    platform_type=platform_type,
                    labels={"process.name": process_name},
                )
                self.assertEqual(routing.public_http_endpoints(config), [])


class DeploymentValidatorContracts(unittest.TestCase):
    def valid_config(self, **changes):
        values = dict(
            name="demo-app",
            tag="v1-0",
            zip_path="",
            dockerfile_template="FROM python:3.12",
            max_cpu=1.0,
            max_ram=512,
            networks=[NetworkSpec(name="demo-network")],
            volumes=[],
            port=8000,
            read_only=False,
            platform="python",
            platform_type="app",
        )
        values.update(changes)
        return DeploymentConfig(**values)

    def test_valid_deployment_config_passes(self):
        from deployments.core.validation import DeploymentValidator

        with tempfile.NamedTemporaryFile() as tmp:
            config = self.valid_config(zip_path=tmp.name)
            DeploymentValidator().validate(config)

    def test_validator_aggregates_independent_errors(self):
        from deployments.core.validation import DeploymentValidator

        config = self.valid_config(
            name="INVALID NAME",
            tag="",
            zip_path="/does/not/exist",
            max_cpu=0,
            max_ram=0,
            port=70000,
            networks=[NetworkSpec(name="BAD NETWORK")],
        )
        with self.assertRaises(DeploymentValidationError) as ctx:
            DeploymentValidator().validate(config)
        errors = ctx.exception.details["errors"]
        self.assertGreaterEqual(len(errors), 6)
        self.assertTrue(any("Image tag" in item for item in errors))
        self.assertTrue(any("CPU limit" in item for item in errors))
        self.assertTrue(any("RAM limit" in item for item in errors))
        self.assertTrue(any("port" in item.lower() for item in errors))

    def test_volume_validation_rejects_bad_target_mode_and_source(self):
        from deployments.core.validation import DeploymentValidator

        volume = VolumeSpec(
            source="BAD VOLUME",
            target="relative/path",
            mode="execute",
            mount_type="volume",
            size_mb=0,
        )
        config = self.valid_config(volumes=[volume])
        with tempfile.NamedTemporaryFile() as tmp:
            config = DeploymentConfig(**{**config.__dict__, "zip_path": tmp.name})
            with self.assertRaises(DeploymentValidationError) as ctx:
                DeploymentValidator().validate(config)
        errors = ctx.exception.details["errors"]
        self.assertTrue(any("mount type" not in item.lower() and "mode" in item.lower() for item in errors))
        self.assertTrue(any("absolute container path" in item for item in errors))
        self.assertTrue(any("volume name" in item.lower() for item in errors))

    def test_volume_capacity_must_be_positive(self):
        from deployments.core.validation import DeploymentValidator

        volume = VolumeSpec(source="data", target="/data", size_mb=0)
        with tempfile.NamedTemporaryFile() as tmp:
            config = self.valid_config(zip_path=tmp.name, volumes=[volume])
            with self.assertRaises(DeploymentValidationError) as ctx:
                DeploymentValidator().validate(config)
        self.assertTrue(any("size must be greater than zero" in item.lower() for item in ctx.exception.details["errors"]))


class VolumeAndCleanupContracts(unittest.TestCase):
    def test_named_volume_is_created_and_mapped(self):
        from deployments.core import volumes

        fake = MagicMock()
        with patch.object(volumes, "Volume", return_value=fake) as ctor:
            result = volumes.VolumeMountManager().prepare([
                VolumeSpec(source="demo-data", target="/data", mode="ro", size_mb=128)
            ])
        self.assertEqual(result, {"demo-data": {"bind": "/data", "mode": "ro"}})
        ctor.assert_called_once()
        fake.ensure.assert_called_once()

    def test_duplicate_volume_targets_are_rejected_before_docker_calls(self):
        from deployments.core import volumes

        first = VolumeSpec(source="one", target="/data")
        second = VolumeSpec(source="two", target="/data")
        with patch.object(volumes, "Volume") as ctor:
            with self.assertRaises(VolumeError) as ctx:
                volumes.VolumeMountManager().prepare([first, second])
        self.assertIn("Duplicate volume target", str(ctx.exception))
        ctor.assert_not_called()

    def test_host_bind_source_is_validated(self):
        from deployments.core import volumes

        with patch.object(volumes, "validate_bind_source", side_effect=DeploymentSecurityError("blocked")):
            with self.assertRaises(DeploymentSecurityError):
                volumes.VolumeMountManager().prepare([
                    VolumeSpec(source="/etc", target="/data", mount_type="bind")
                ])

    def test_invalid_volume_mode_is_rejected_before_storage_creation(self):
        from deployments.core import volumes

        with patch.object(volumes, "Volume") as ctor:
            with self.assertRaises(VolumeError) as ctx:
                volumes.VolumeMountManager().prepare([
                    VolumeSpec(source="data", target="/data", mode="execute")
                ])
        self.assertIn("Unsupported volume mode", str(ctx.exception))
        ctor.assert_not_called()

    def test_cleanup_does_not_globally_prune_shared_docker_host(self):
        from deployments.core.cleanup import CleanupManager

        logger = MagicMock()
        result = CleanupManager(logger=logger).prune_dangling_images()
        self.assertFalse(result)
        logger.info.assert_called_once()
        message = logger.info.call_args.args[1]
        self.assertIn("Skipped global dangling-image prune", message)


if __name__ == "__main__":
    unittest.main()
