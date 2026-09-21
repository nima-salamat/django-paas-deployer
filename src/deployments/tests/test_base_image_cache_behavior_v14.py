from pathlib import Path


def test_base_image_auto_build_uses_docker_cache_unless_forced():
    text = Path("deploy/base_images.py").read_text()
    assert '"no_cache": bool((build_policy or {}).get("force_rebuild", False))' in text


def test_base_image_cache_hit_requires_ready_local_and_no_rebuild_request():
    text = Path("deploy/base_images.py").read_text()
    assert 'row.status == BaseRuntimeImage.Status.READY and local_exists and not row.rebuild_requested' in text


def test_php_base_skips_extensions_already_enabled():
    text = Path("deploy/base_images.py").read_text()
    assert 'PHP extension ${ext} already enabled; skipping build' in text
    assert 'docker-php-ext-install -j$(nproc) $missing' in text
