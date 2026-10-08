import io
import tarfile

import docker
import pytest

from deployments.core.manager import client_manager, image_manager


def _empty_tar():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w"):
        pass
    stream.seek(0)
    return stream


class _FakeSlot:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def assert_owned(self):
        return None


class _FakeImages:
    def __init__(self):
        self.image = type(
            "FakeImage",
            (),
            {
                "id": "sha256:0123456789abcdef",
                "attrs": {"RepoDigests": ["test/repo@sha256:digest"], "Config": {"Labels": {}}},
            },
        )()

    def get(self, ref):
        return self.image


class _FakeDockerClient:
    def __init__(self, api):
        self.api = api
        self.images = _FakeImages()
        self.closed = False

    def ping(self):
        return True

    def version(self):
        return {
            "Version": "29.0.0",
            "ApiVersion": "1.52",
            "MinAPIVersion": "1.40",
            "Os": "linux",
            "Arch": "amd64",
        }

    def close(self):
        self.closed = True


class _UnsupportedBuildOption(docker.errors.APIError):
    @property
    def status_code(self):
        return 400

    def __str__(self):
        return self.args[0] if self.args else "unsupported build option"


def _patch_image_client(monkeypatch, clients):
    iterator = iter(clients)

    def factory(*args, **kwargs):
        return next(iterator)

    monkeypatch.setattr(client_manager, "get_docker_client", factory)
    monkeypatch.setattr(image_manager, "BuildSlot", _FakeSlot)


def test_docker_client_uses_api_version_negotiation(monkeypatch):
    created = []

    class FakeDockerClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def ping(self):
            return True

        def close(self):
            return None

    monkeypatch.setattr(client_manager.docker, "DockerClient", FakeDockerClient)
    monkeypatch.setattr(client_manager, "retry_with_backoff", lambda *args, **kwargs: args[0]())

    client_manager.reset_docker_client()
    client_manager.get_docker_client(
        "unix:///var/run/docker.sock",
        cluster="test-cluster",
    )

    assert created
    assert created[0]["version"] == "auto"
    client_manager.reset_docker_client()


def test_build_falls_back_when_engine_rejects_optional_build_controls(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                def fail_before_stream():
                    raise _UnsupportedBuildOption("unsupported container_limits parameter")
                    yield  # pragma: no cover
                return fail_before_stream()
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    api = FakeApi()
    client = _FakeDockerClient(api)
    _patch_image_client(monkeypatch, [client])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )
    image.create()

    assert len(api.calls) == 2
    assert "container_limits" in api.calls[0]
    assert "shmsize" in api.calls[0]
    assert "container_limits" not in api.calls[1]
    assert "shmsize" not in api.calls[1]
    assert "network_mode" not in api.calls[0]
    assert "network_mode" not in api.calls[1]

def test_build_sends_full_repository_and_tag_to_docker_api(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    api = FakeApi()
    client = _FakeDockerClient(api)
    _patch_image_client(monkeypatch, [client])

    image = image_manager.Image(
        "app/example-service",
        "20261008",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )
    image.create()

    assert api.calls
    assert api.calls[0]["tag"] == "app/example-service:20261008"





def test_http_400_build_request_is_retried_with_minimal_profile(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                def fail_before_stream():
                    error = docker.errors.APIError("Bad parameter", response=None)
                    error.status_code = 400
                    raise error
                    yield  # pragma: no cover
                return fail_before_stream()
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    api = FakeApi()
    client = _FakeDockerClient(api)
    _patch_image_client(monkeypatch, [client])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )
    image.create()

    assert len(api.calls) == 2
    assert "container_limits" in api.calls[0]
    assert "shmsize" in api.calls[0]
    assert "container_limits" not in api.calls[1]
    assert "shmsize" not in api.calls[1]

def test_transient_build_transport_failure_refreshes_client_once(monkeypatch):
    class FailingApi:
        def __init__(self):
            self.calls = 0

        def build(self, **kwargs):
            self.calls += 1
            def fail_before_stream():
                raise ConnectionError("connection reset by peer")
                yield  # pragma: no cover
            return fail_before_stream()

    class WorkingApi:
        def __init__(self):
            self.calls = 0

        def build(self, **kwargs):
            self.calls += 1
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    first = _FakeDockerClient(FailingApi())
    second = _FakeDockerClient(WorkingApi())
    _patch_image_client(monkeypatch, [first, second])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )
    image.create()

    assert first.api.calls == 1
    assert second.api.calls == 1
    assert first.closed is True


def test_build_failure_from_stream_is_not_retried_as_transport_failure(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.calls = 0

        def build(self, **kwargs):
            self.calls += 1
            return [{"error": "Dockerfile syntax error"}]

    api = FakeApi()
    client = _FakeDockerClient(api)
    _patch_image_client(monkeypatch, [client])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )

    with pytest.raises(image_manager.ImageBuildError) as exc_info:
        image.create()

    assert api.calls == 1
    assert exc_info.value.details["docker_api_reached"] is True


def test_docker_diagnostics_report_client_and_server_api_versions():
    api = type("Api", (), {"_version": "1.52"})()
    client = type(
        "Client",
        (),
        {
            "api": api,
            "version": lambda self: {
                "Version": "29.0.0",
                "ApiVersion": "1.52",
                "MinAPIVersion": "1.40",
                "Os": "linux",
                "Arch": "amd64",
            },
        },
    )()

    result = client_manager.docker_client_diagnostics(client, include_version=True)

    assert result["sdk_version"]
    assert result["client_api_version"] == "1.52"
    assert result["server_version"] == "29.0.0"
    assert result["server_api_version"] == "1.52"
    assert result["server_min_api_version"] == "1.40"


def test_generator_build_request_errors_are_recovered_before_stream(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            def fail_before_stream():
                raise _UnsupportedBuildOption("unsupported shmsize parameter")
                yield  # pragma: no cover
            if len(self.calls) == 1:
                return fail_before_stream()
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    api = FakeApi()
    client = _FakeDockerClient(api)
    _patch_image_client(monkeypatch, [client])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )

    image.create()

    assert len(api.calls) == 2
    assert "shmsize" in api.calls[0]
    assert "shmsize" not in api.calls[1]


def test_generator_transport_error_is_retried_before_stream(monkeypatch):
    class FailingApi:
        def build(self, **kwargs):
            def fail_before_stream():
                raise ConnectionError("connection reset by peer")
                yield  # pragma: no cover
            return fail_before_stream()

    class WorkingApi:
        def build(self, **kwargs):
            return iter([{"aux": {"ID": "sha256:0123456789abcdef"}}])

        def tag(self, *args, **kwargs):
            return True

    first = _FakeDockerClient(FailingApi())
    second = _FakeDockerClient(WorkingApi())
    _patch_image_client(monkeypatch, [first, second])

    image = image_manager.Image(
        "test/repo",
        "v1",
        "FROM alpine\nCMD [\"true\"]",
        _empty_tar(),
    )
    image.create()

    assert first.closed is True
