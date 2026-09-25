from types import SimpleNamespace


def test_force_cancel_cleanup_targets_deployment_image(monkeypatch):
    from services.api import runtime

    class Images:
        def __init__(self): self.removed=[]
        def remove(self, ref, force=True): self.removed.append(ref)
    class Containers:
        def list(self, all=True): return []
    images=Images(); client=SimpleNamespace(images=images, containers=Containers())
    monkeypatch.setattr(runtime, "Client", lambda: (lambda: client))
    monkeypatch.setattr(runtime, "DockerNotFound", type("DNF", (Exception,), {}))
    monkeypatch.setattr("deployments.celery.services.deploy_service._docker_safe_tag", lambda v: "v" + str(v).replace('.', '-'))
    service=SimpleNamespace(id=SimpleNamespace(hex="12345678"), get_docker_service_name=lambda: "svc")
    deploy=SimpleNamespace(pk=42, version="1.20")
    report=runtime._force_cancel_runtime_cleanup(service, container_name="svc", deploy=deploy)
    assert images.removed == ["svc:v1-20"]
    assert not any(i.get("ref") == "svc:latest" for i in report["images"])
