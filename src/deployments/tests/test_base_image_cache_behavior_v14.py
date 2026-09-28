from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_base_image_auto_build_uses_docker_cache_unless_forced():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    assert (
        '"no_cache": bool(force_rebuild)' in text
        or '"no_cache": bool(requested_force_rebuild)' in text
    )


def test_base_image_cache_hit_requires_compatible_local_image_and_definition():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    assert "_can_use_compatible_local_base_image(" in text
    assert "row.definition_fingerprint == fingerprint" in text


def test_php_base_skips_extensions_already_enabled():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    # This is a Python f-string template, so the rendered shell `${ext}` is
    # intentionally represented by `${{ext}}` in source.
    assert 'PHP extension ${{ext}} already enabled; skipping build' in text
    assert 'docker-php-ext-install -j$(nproc) $missing' in text

def test_compatible_local_base_image_is_usable_while_registry_build_is_in_progress():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_compatible_local_base_image

    row = SimpleNamespace(
        definition_fingerprint="fp",
        status="building",
        rebuild_requested=True,
    )

    assert _can_use_compatible_local_base_image(
        row,
        "fp",
        local_exists=True,
        local_compatible=True,
    )


def test_incompatible_or_missing_local_base_image_is_not_usable():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_compatible_local_base_image

    row = SimpleNamespace(
        definition_fingerprint="fp",
        status="building",
        rebuild_requested=True,
    )

    assert not _can_use_compatible_local_base_image(
        row,
        "different",
        local_exists=True,
        local_compatible=True,
    )
    assert not _can_use_compatible_local_base_image(
        row,
        "fp",
        local_exists=False,
        local_compatible=True,
    )
    assert not _can_use_compatible_local_base_image(
        row,
        "fp",
        local_exists=True,
        local_compatible=False,
    )


def test_local_base_image_resolution_checks_docker_fingerprint_even_when_rebuild_requested():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    section = text.split("def ensure_base_images", 1)[1]
    resolution = section.split("def release_stale_base_image_leases", 1)[0]

    assert "_local_image_matches_fingerprint(row.image_ref, fingerprint)" in resolution
    assert "_can_use_compatible_local_base_image(" in resolution
    assert 'policy["auto_register_existing"]' in resolution
    assert "row.status != BaseRuntimeImage.Status.BUILDING" in resolution
    assert '"registry_status": row.status' in resolution
