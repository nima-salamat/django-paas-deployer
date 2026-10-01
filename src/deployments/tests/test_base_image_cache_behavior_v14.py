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
    assert "_local_image_matches_fingerprint(" in text
    assert "_can_use_compatible_local_base_image(" in text
    assert 'policy["auto_register_existing"]' in resolution
    assert "row.status != BaseRuntimeImage.Status.BUILDING" in resolution
    assert '"registry_status": row.status' in resolution
def test_last_known_good_local_base_image_is_usable_when_renewal_failed():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_last_known_good_local_base_image

    row = SimpleNamespace(
        image_id="sha256:good",
        logical_runtime="php",
        runtime_version="8.4",
        variant="apache",
        status="failed",
        rebuild_requested=True,
    )
    local_image = SimpleNamespace(id="sha256:good", attrs={"Config": {"Labels": {}}})

    assert _can_use_last_known_good_local_base_image(
        row,
        local_image=local_image,
        expected_runtime="php:8.4:apache",
    )


def test_last_known_good_local_base_image_can_use_runtime_identity_label():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_last_known_good_local_base_image

    row = SimpleNamespace(
        image_id="",
        logical_runtime="php",
        runtime_version="8.4",
        variant="apache",
        status="building",
        rebuild_requested=True,
    )
    local_image = SimpleNamespace(
        id="sha256:old",
        attrs={"Config": {"Labels": {"io.passdeployer.base-runtime": "php:8.4:apache"}}},
    )

    assert _can_use_last_known_good_local_base_image(
        row,
        local_image=local_image,
        expected_runtime="php:8.4:apache",
    )


def test_definition_change_preserves_last_known_good_image_identity():
    text = (ROOT / "deploy/base_images.py").read_text(encoding="utf-8")
    assert "Keep image_id/image_digest as the last-known-good local" in text
def test_unlabelled_local_base_image_is_usable_as_operator_fallback_when_not_ready():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_last_known_good_local_base_image

    row = SimpleNamespace(
        image_id="",
        logical_runtime="php",
        runtime_version="8.4",
        variant="apache",
        status="failed",
        rebuild_requested=True,
    )
    local_image = SimpleNamespace(id="sha256:old", attrs={"Config": {"Labels": {}}})

    assert _can_use_last_known_good_local_base_image(
        row,
        local_image=local_image,
        expected_runtime="php:8.4:apache",
    )


def test_ready_row_does_not_accept_unverified_local_base_image():
    from types import SimpleNamespace

    from deploy.base_images import _can_use_last_known_good_local_base_image

    row = SimpleNamespace(
        image_id="",
        logical_runtime="php",
        runtime_version="8.4",
        variant="apache",
        status="ready",
        rebuild_requested=False,
    )
    local_image = SimpleNamespace(id="sha256:old", attrs={"Config": {"Labels": {}}})

    assert not _can_use_last_known_good_local_base_image(
        row,
        local_image=local_image,
        expected_runtime="php:8.4:apache",
    )