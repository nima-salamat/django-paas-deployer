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

    assert 'Concurrent base image build failed: {image_ref}.' in source
    assert 'Concurrent base image build timed out: {image_ref}' in source
