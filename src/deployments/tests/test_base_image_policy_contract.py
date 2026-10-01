import io


def _empty_tar():
    import tarfile
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w"):
        pass
    stream.seek(0)
    return stream


def test_image_none_and_empty_policy_are_resolved_before_build():
    import deployments.core.manager.image_manager as image_manager

    class FakeApi:
        def __init__(self):
            self.build_calls = []
        def build(self, **kwargs):
            self.build_calls.append(kwargs)
            return [{"aux": {"ID": "sha256:0123456789abcdef"}}]
        def tag(self, *args, **kwargs):
            return True

    class FakeImage:
        id = "sha256:0123456789abcdef"
        attrs = {"RepoDigests": ["test/repo@sha256:digest"], "Config": {"Labels": {}}}

    class FakeImages:
        def __init__(self, api):
            self.api = api
        def get(self, ref):
            return FakeImage()

    class FakeClient:
        def __init__(self):
            self.api = FakeApi()
            self.images = FakeImages(self.api)

    class FakeSlot:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def assert_owned(self):
            return None

    client = FakeClient()
    import deployments.core.manager.client_manager as client_manager
    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(client_manager, "get_docker_client", lambda base_url=None, **kwargs: client)
        monkeypatch.setattr(image_manager, "BuildSlot", FakeSlot)
        image_none = image_manager.Image(
            "test/repo", "v1", "FROM alpine\nCMD [\"true\"]", _empty_tar(),
            build_resource_policy=None,
        )
        image_empty = image_manager.Image(
            "test/repo2", "v1", "FROM alpine\nCMD [\"true\"]", _empty_tar(),
            build_resource_policy={},
        )
        for image in (image_none, image_empty):
            assert {"cpu", "memory_mb", "pids_limit", "shm_size_mb", "mode"} <= set(image.build_resource_policy)
            image.create()
        assert len(client.api.build_calls) == 2
    finally:
        monkeypatch.undo()


def test_force_rebuild_is_not_forwarded_as_a_resource_field():
    import deployments.common.resource_policy as policy
    resolved = policy.resolve_build_policy({})
    assert "force_rebuild" not in resolved


def test_legacy_force_rebuild_only_policy_is_resolved_before_image_build():
    import deployments.common.resource_policy as policy
    canonical = {
        "cpu": 1.0,
        "memory_mb": 1024,
        "pids_limit": 2048,
        "shm_size_mb": 64,
        "mode": "static",
    }
    original = policy.build_limits
    try:
        policy.build_limits = lambda plan=None: dict(canonical)
        import pytest
        with pytest.raises(ValueError, match="force_rebuild"):
            policy.resolve_build_policy({"force_rebuild": False})
    finally:
        policy.build_limits = original
