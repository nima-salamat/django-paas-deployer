"""
Tests for ``ContainerSnapshot`` (rollback state capture).

The full ``restore_from_snapshot`` path requires a Docker daemon, so we
test only the dataclass + the parts of ``capture`` that don't need a
live container.  The actual restore flow is exercised by integration
tests in CI.
"""

import unittest
from unittest.mock import patch, MagicMock

from deployments.core.rollback import ContainerSnapshot, RollbackManager
from deployments.common.exceptions import RollbackError


def _mock_docker_client():
    """Return a MagicMock that stands in for a DockerClient."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    return mock_client


class TestContainerSnapshotDataclass(unittest.TestCase):

    def test_empty_snapshot(self):
        snap = ContainerSnapshot.empty("my-service")
        self.assertEqual(snap.name, "my-service")
        self.assertIsNone(snap.image_ref)
        self.assertEqual(snap.environment, {})
        self.assertEqual(snap.networks, [])
        self.assertEqual(snap.binds, {})

    def test_snapshot_fields_default_to_safe_values(self):
        snap = ContainerSnapshot(name="svc", image_ref="img:1")
        self.assertTrue(snap.read_only)  # safe default
        self.assertEqual(snap.max_cpu, None)
        self.assertEqual(snap.max_ram, None)


class TestContainerSnapshotCapture(unittest.TestCase):

    def test_capture_returns_empty_for_missing_container(self):
        from deployments.core.manager.container_manager import Container
        with patch(
            "deployments.core.manager.client_manager.get_docker_client",
            return_value=_mock_docker_client(),
        ), patch.object(Container, "exists", return_value=False):
            container = Container("test-svc")
            snap = ContainerSnapshot.capture(container)
        self.assertIsNone(snap.image_ref)
        self.assertEqual(snap.name, "test-svc")

    def test_capture_extracts_state_from_inspect_payload(self):
        from deployments.core.manager.container_manager import Container
        inspect_payload = {
            "Config": {
                "Image": "myimg:1",
                "Env": ["DATABASE_URL=postgres://x", "SECRET_KEY=abc"],
                "Cmd": ["gunicorn", "app:app"],
                "Labels": {
                    "managed-by": "django-paas-deployer",
                    "traefik.http.routers.myservice.rule": "Host(`myservice.example.com`)",
                },
                "ExposedPorts": {"8000/tcp": {}},
            },
            "HostConfig": {
                "CpuQuota": 100000,
                "CpuPeriod": 100000,
                "Memory": 536870912,  # 512 MB
                "Binds": ["/srv/data:/data:rw"],
                "ReadonlyRootfs": True,
                "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 5},
                "PortBindings": {"8000/tcp": [{"HostPort": "0"}]},
            },
            "NetworkSettings": {
                "Networks": {"proxy_net": {}, "app_net": {}},
            },
        }
        with patch(
            "deployments.core.manager.client_manager.get_docker_client",
            return_value=_mock_docker_client(),
        ), patch.object(Container, "exists", return_value=True), \
             patch.object(Container, "inspect", return_value=inspect_payload), \
             patch.object(Container, "get_image_identifier", return_value="sha256:abc"):
            container = Container("myservice")
            snap = ContainerSnapshot.capture(container)

        self.assertEqual(snap.name, "myservice")
        self.assertEqual(snap.image_ref, "sha256:abc")
        self.assertEqual(snap.environment, {
            "DATABASE_URL": "postgres://x",
            "SECRET_KEY": "abc",
        })
        self.assertEqual(snap.command, "gunicorn app:app")
        self.assertEqual(snap.networks, ["proxy_net", "app_net"])
        self.assertEqual(snap.binds, {"/srv/data": {"bind": "/data", "mode": "rw"}})
        self.assertTrue(snap.read_only)
        self.assertEqual(snap.entry_port, 8000)
        self.assertEqual(snap.max_cpu, 1.0)
        self.assertEqual(snap.max_ram, 512)
        self.assertEqual(snap.restart_policy["Name"], "unless-stopped")
        self.assertEqual(snap.route_name, "myservice")  # from labels


class TestRollbackManagerRestore(unittest.TestCase):

    def test_restore_returns_false_when_no_image(self):
        from deployments.core.manager.container_manager import Container
        with patch(
            "deployments.core.manager.client_manager.get_docker_client",
            return_value=_mock_docker_client(),
        ):
            manager = RollbackManager(logger=MagicMock())
            snap = ContainerSnapshot.empty("svc")  # image_ref=None
            result = manager.restore_from_snapshot(snap)
        self.assertFalse(result)

    def test_restore_raises_on_failure(self):
        """When restore itself fails, RollbackError must propagate."""
        from deployments.core.manager.container_manager import Container
        snap = ContainerSnapshot(
            name="svc",
            image_ref="img:1",
            networks=["proxy_net"],
            binds={"/srv/data": {"bind": "/data", "mode": "rw"}},
        )

        # Make Container(...).exists() raise during restore.
        with patch(
            "deployments.core.manager.client_manager.get_docker_client",
            return_value=_mock_docker_client(),
        ), patch.object(Container, "exists", side_effect=RuntimeError("docker down")):
            manager = RollbackManager(logger=MagicMock())
            with self.assertRaises(RollbackError) as ctx:
                manager.restore_from_snapshot(snap)
        self.assertIn("Rollback failed", str(ctx.exception))
        self.assertEqual(ctx.exception.details["previous_image_ref"], "img:1")


if __name__ == "__main__":
    unittest.main()
