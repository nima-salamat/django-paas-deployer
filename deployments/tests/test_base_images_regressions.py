from pathlib import Path


def test_base_image_registry_model_and_runtime_hooks_exist():
    root = Path(__file__).resolve().parents[2]
    assert (root / "deploy" / "base_images.py").is_file()
    assert "class BaseRuntimeImage" in (root / "deploy" / "models.py").read_text()
    assert "ensure_base_images" in (root / "deploy" / "base_images.py").read_text()
    assert "BaseRuntimeImage" in (root / "deploy" / "admin.py").read_text()
    assert "build_base_runtime_image" in (root / "deployments" / "celery" / "tasks.py").read_text()


def test_renderer_has_cached_runtime_base_replacement():
    text = (Path(__file__).resolve().parents[1] / "core" / "dockerfile.py").read_text()
    assert "_apply_resolved_base_images" in text
    assert "node_base_image" in text
    assert "nginx_base_image" in text


def test_rebuild_uses_no_cache_and_pull():
    text = (Path(__file__).resolve().parents[2] / "deploy" / "base_images.py").read_text()
    assert '"pull": True' in text
    assert '"no_cache": True' in text
