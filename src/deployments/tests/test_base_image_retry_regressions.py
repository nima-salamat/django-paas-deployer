from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_base_image_retry_keeps_record_in_building_state():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")

    assert "BaseRuntimeImage.Status.BUILDING" in source
    assert 'build_task_id=str(self.request.id)' in source
    assert "build_completed_at=None" in source
    assert "raise self.retry(exc=exc)" in source


def test_base_image_wait_surfaces_persisted_builder_failure_reason():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")

    assert 'current["status"] == BaseRuntimeImage.Status.FAILED' in source
    assert 'current.get("last_error")' in source
    assert 'Base image build failed: {spec.image_ref}.' in source
    assert 'Base image build timed out: {spec.image_ref}' in source


def test_concurrent_base_image_wait_surfaces_failure_reason():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")

    assert '"waiting_for_concurrent": waiting_for_concurrent' in source
    assert 'Base image build failed: {image_ref}.' in source
    assert 'Base image wait timed out: {image_ref}.' in source


def test_retry_helper_persists_building_not_failed(monkeypatch):
    import deployments.celery.tasks as tasks

    events = []
    class Query:
        def __init__(self, first_value=None):
            self.first_value = first_value
        def values_list(self, *args, **kwargs):
            return self
        def first(self):
            return self.first_value
        def update(self, **kwargs):
            events.append(kwargs)
            return 1
        def values(self, *args, **kwargs):
            return self
    class Objects:
        def filter(self, **kwargs):
            return Query(first_value="paas-base/php-apache-root:8.4-r1")
    class FakeStatus:
        BUILDING = "building"
        FAILED = "failed"
    class FakeBase:
        Status = FakeStatus
        objects = Objects()
    monkeypatch.setattr(tasks, "BaseRuntimeImage", FakeBase)
    tasks._mark_base_image_retry_pending("1", "task-1", RuntimeError("docker failed"))
    assert events
    assert events[-1]["status"] == FakeStatus.BUILDING
    assert events[-1]["last_error_details"]["retry_pending"] is True
    assert events[-1]["status"] != FakeStatus.FAILED


def test_build_registered_base_failure_does_not_become_terminal_before_celery_exhaustion(monkeypatch):
    import deploy.base_images as base_images

    class Row:
        pk = "1"
        status = "pending"
        build_task_id = ""
        build_owner_deployment_id = "deploy-1"
        rebuild_requested = False
        logical_runtime = "php"
        runtime_version = "8.4"
        variant = "apache-root"
        definition_fingerprint = ""
        build_started_at = None
        build_completed_at = None
        last_error = ""
        last_error_details = {}
        image_ref = "paas-base/php-apache-root:8.4-r1"
        image_id = ""
        image_digest = ""
        build_count = 0
        def save(self, **kwargs): return None

    class Query:
        def __init__(self, row): self.row = row
        def select_for_update(self): return self
        def get(self, **kwargs): return self.row
        def filter(self, **kwargs): return self
        def update(self, **kwargs):
            for k, v in kwargs.items(): setattr(self.row, k, v)
            return 1

    class FakeBase:
        class Status:
            BUILDING = "building"
            READY = "ready"
            FAILED = "failed"
        objects = Query(Row())

    spec = base_images._php("8.4", public_root=False)
    monkeypatch.setattr(base_images, "BaseRuntimeImage", FakeBase)
    monkeypatch.setattr(base_images, "_spec_for_record", lambda row: spec)
    monkeypatch.setattr(base_images, "_spec_fingerprint", lambda spec: "fingerprint")
    monkeypatch.setattr(base_images, "_build_spec", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("docker failed")))
    with __import__("pytest").raises(RuntimeError, match="docker failed"):
        base_images.build_registered_base_image(
            "1", task_id="task-1", build_policy={}
        )
    assert FakeBase.objects.row.status == FakeBase.Status.BUILDING
    assert FakeBase.objects.row.last_error_details["retry_pending"] is None
