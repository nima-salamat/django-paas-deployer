from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_base_image_auto_build_uses_docker_cache_unless_forced():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    assert '"no_cache": bool((build_policy or {}).get("force_rebuild", False))' in text


def test_base_image_cache_hit_requires_ready_local_and_no_rebuild_request():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    assert 'row.status == BaseRuntimeImage.Status.READY and local_exists and not row.rebuild_requested' in text


def test_php_base_skips_extensions_already_enabled():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    # This is a Python f-string template, so the rendered shell `${ext}` is
    # intentionally represented by `${{ext}}` in source.
    assert 'PHP extension ${{ext}} already enabled; skipping build' in text
    assert 'docker-php-ext-install -j$(nproc) $missing' in text
