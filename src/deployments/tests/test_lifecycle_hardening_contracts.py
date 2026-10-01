"""Regression contracts for lifecycle hardening changes."""

from datetime import datetime, timedelta, timezone

from deployments.common.deadline import DeploymentDeadline
from deployments.common.retry import classify_docker_exception
from deployments.common.exceptions import DeploymentError, FailureDomain, Retryability
from deployments.planning.runtime_spec import RuntimeSpec


def test_deadline_bounds_nested_operation_to_remaining_budget():
    now = datetime.now(timezone.utc)
    deadline = DeploymentDeadline(deadline=now + timedelta(seconds=3))
    assert 0 < deadline.bound(30, now=now) <= 3


def test_docker_400_is_not_retryable_but_503_is():
    class FakeDockerError(Exception):
        pass

    permanent = FakeDockerError("invalid mount")
    permanent.status_code = 400
    transient = FakeDockerError("daemon busy")
    transient.status_code = 503
    assert classify_docker_exception(permanent, stage="container_create").retryable is False
    assert classify_docker_exception(transient, stage="container_create").retryable is True


def test_runtime_spec_redacts_secret_environment_values_and_is_stable():
    config = type("Config", (), {
        "image_ref": "demo:1",
        "environment": {"APP_ENV": "production", "DB_PASSWORD": "super-secret"},
        "labels": {"service.id": "svc", "deployment.id": "dep"},
        "networks": [],
        "volumes": [],
        "endpoints": [],
        "read_only": True,
        "resource_limits": {"cpu": 1, "memory_mb": 256},
        "healthcheck_path": "/health",
        "healthcheck_expected_status": (200,),
        "healthcheck_timeout": 5,
        "health_interval": 1,
        "runtime_options": {},
        "start_command": "gunicorn app:wsgi",
        "entry_point": None,
        "public_host": "demo.example.test",
        "port": 8000,
    })()
    spec = RuntimeSpec.from_config(config, image_ref="demo:1", image_digest="sha256:abc", revision_id="rev1")
    payload = spec.as_dict()
    assert payload["environment"]["DB_PASSWORD"] == "[SECRET_REF]"
    assert payload["secret_references"] == ["DB_PASSWORD"]
    assert spec.sha256 == RuntimeSpec.from_config(config, image_ref="demo:1", image_digest="sha256:abc", revision_id="rev1").sha256


def test_failure_taxonomy_distinguishes_user_input_from_transient_infrastructure():
    bad_config = DeploymentError("invalid configuration", code="deployment_validation_failed", recoverable=False)
    assert bad_config.failure_domain == str(FailureDomain.USER_INPUT)
    assert bad_config.retryability == str(Retryability.NEVER)

    transient = DeploymentError("daemon unavailable", code="docker_daemon_unavailable", recoverable=True)
    assert transient.failure_domain == str(FailureDomain.RUNTIME_APP)
    assert transient.retryability == str(Retryability.BACKOFF)


def test_terminal_outbox_authority_is_not_in_public_transition():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = (root / "deployments" / "core" / "state" / "manager.py").read_text(encoding="utf-8")
    public = source.split("def transition_deploy(", 1)[1].split("def lock_and_get_deployment", 1)[0]
    assert "DeploymentEventOutbox.objects.create" not in public
    assert "terminal" not in public
    assert "DeploymentEventOutbox.objects.create" in source.split("def transition_deploy_if_owned", 1)[1]
