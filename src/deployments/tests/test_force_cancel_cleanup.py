from types import SimpleNamespace


def test_force_cancel_cleanup_does_not_remove_a_shared_deployment_image(monkeypatch):
    from services.api import runtime

    class Images:
        def __init__(self): self.removed=[]
        def remove(self, ref, force=True): self.removed.append(ref)
    class Containers:
        def list(self, all=True): return []
    images=Images(); client=SimpleNamespace(images=images, containers=Containers())
    monkeypatch.setattr(runtime, "swarm_enabled", lambda: False)
    monkeypatch.setattr(runtime, "Client", lambda: (lambda: client))
    monkeypatch.setattr(runtime, "DockerNotFound", type("DNF", (Exception,), {}))
    monkeypatch.setattr(
        "deployments.celery.services.deploy_service._docker_tag_from_deploy",
        lambda v: str(v),
    )
    service=SimpleNamespace(id=SimpleNamespace(hex="12345678"), get_docker_service_name=lambda: "svc")
    deploy=SimpleNamespace(pk=42, version="1.20")
    report=runtime._force_cancel_runtime_cleanup(service, container_name="svc", deploy=deploy)
    assert images.removed == []
    assert report["images"] == []


def test_force_cancel_cleanup_stops_before_runtime_access_after_lifecycle_loss(monkeypatch):
    import pytest

    from deployments.common.exceptions import StaleDeploymentWorkerError
    from services.api import runtime

    service = SimpleNamespace(pk="service-1", active_revision_id=None)
    deploy = SimpleNamespace(pk=42)
    monkeypatch.setattr(
        runtime,
        "Client",
        lambda: pytest.fail("stale cleanup must not connect to Docker"),
    )

    with pytest.raises(StaleDeploymentWorkerError):
        runtime._force_cancel_runtime_cleanup(
            service,
            container_name="svc",
            deploy=deploy,
            ownership_check=lambda: False,
        )
