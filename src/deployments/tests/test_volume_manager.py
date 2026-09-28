"""Regression tests for Docker host filesystem space checks."""

from types import SimpleNamespace

import deployments.core.manager.client_manager as client_manager
import deployments.core.manager.volume_manager as volume_manager


def test_check_host_space_uses_configured_host_storage_path(monkeypatch):
    observed = []

    monkeypatch.setenv("DOCKER_HOST_STORAGE_PATH", "/host-docker-root")
    monkeypatch.setattr(
        client_manager,
        "Client",
        lambda: SimpleNamespace(
            client=SimpleNamespace(
                info=lambda: {"DockerRootDir": "/var/lib/docker"},
            )
        ),
    )

    def fake_disk_usage(path):
        observed.append(path)
        return SimpleNamespace(free=2 * 1024 * 1024 * 1024)

    monkeypatch.setattr(volume_manager.shutil, "disk_usage", fake_disk_usage)

    ok, free_mb = volume_manager.Volume.check_host_space(required_mb=1024)

    assert ok is True
    assert free_mb == 2048
    assert observed == ["/host-docker-root"]
