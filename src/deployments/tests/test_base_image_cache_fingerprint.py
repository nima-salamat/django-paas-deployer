from types import SimpleNamespace


def test_base_image_definition_fingerprint_changes_with_operator_content():
    from deploy.base_images import _php, _spec_fingerprint

    first = _php("8.4")
    second = type(first)(
        first.logical_runtime,
        first.version,
        first.variant,
        first.source_image,
        first.repository,
        first.tag,
        first.dockerfile + "\n# operator security update\n",
    )
    assert _spec_fingerprint(first) != _spec_fingerprint(second)


def test_changed_definition_cannot_adopt_unlabelled_local_image(monkeypatch):
    import deploy.base_images as base_images

    class FakeRow:
        image_ref = "paas-base/php-apache-root:8.4-r1"
        status = "pending"
        image_id = ""
        image_digest = ""
        last_error = ""
        last_error_details = {}
        definition_fingerprint = ""
        def save(self, **kwargs): pass

    class FakeImage:
        id = "sha256:old"
        attrs = {"Config": {"Labels": {}}}

    class FakeClient:
        class Images:
            def get(self, ref): return FakeImage()
        images = Images()

    monkeypatch.setattr(base_images, "_docker_image_exists", lambda ref: True)
    monkeypatch.setattr(base_images, "get_docker_client", lambda: FakeClient())
    assert not base_images._mark_local_image_ready(
        FakeRow(), expected_fingerprint="new-fingerprint"
    )


def test_base_php_cache_tag_remains_stable():
    from deploy.base_images import _php
    assert _php("8.4").image_ref == "paas-base/php-apache:8.4-r1"
