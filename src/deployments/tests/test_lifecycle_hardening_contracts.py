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
    assert bad_config.failure_domain == FailureDomain.USER_INPUT.value
    assert bad_config.retryability == Retryability.NEVER.value

    transient = DeploymentError("daemon unavailable", code="docker_daemon_unavailable", recoverable=True)
    assert transient.failure_domain == FailureDomain.RUNTIME_APP.value
    assert transient.retryability == Retryability.BACKOFF.value


def test_terminal_outbox_authority_is_not_in_public_transition():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = (root / "deployments" / "core" / "state" / "manager.py").read_text(encoding="utf-8")
    public = source.split("def transition_deploy(", 1)[1].split("def lock_and_get_deployment", 1)[0]
    assert "DeploymentEventOutbox.objects.create" not in public
    assert "terminal" not in public
    assert "DeploymentEventOutbox.objects.create" in source.split("def transition_deploy_if_owned", 1)[1]



def test_owned_terminal_transition_rewrites_event_when_cancellation_wins():
    source = ( __import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/state/manager.py" ).read_text(encoding="utf-8")
    method = source.split("def transition_deploy_if_owned", 1)[1].split(
        "def transition_deploy_terminal_if_owned", 1
    )[0]
    assert '"cancellation_won_race": True' in method
    assert '"deployment.cancelled.warning"' in method


def test_pre_start_cancellation_does_not_directly_project_a_second_event():
    source = ( __import__("pathlib").Path(__file__).resolve().parents[2] / "deploy/deployment_state.py" ).read_text(encoding="utf-8")
    start = source.split("def start(self):", 1)[1].split("def event_sink", 1)[0]
    assert "finalize_pending_cancellation" not in start
    assert 'if not emit_cancelled:' in start



def test_system_terminal_transition_owns_state_and_outbox_in_one_transaction():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_deploy_system_terminal", 1)[1].split(
        "def finalize_pending_cancellation", 1
    )[0]
    assert "select_for_update" in method
    assert "check_deploy_transition" in method
    assert "Deploy.objects.filter(pk=deploy_id).update" in method
    assert "DeploymentEventOutbox.objects.create" in method



def test_outbox_dispatcher_uses_deferred_retry_schedule():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/common/event_outbox.py").read_text(encoding="utf-8")
    assert "next_attempt_at__isnull=True" in source
    assert "next_attempt_at__lte=timezone.now()" in source
    assert "backoff_seconds = min(300, 2 ** min(attempts, 8))" in source


def test_monitor_terminal_paths_use_system_owned_terminal_transition():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/celery/monitoring/actions.py").read_text(encoding="utf-8")
    assert source.count("transition_deploy_system_terminal(") >= 3
    assert "DeploymentEventOutbox" not in source



def test_event_sink_keeps_progress_projection_separate_from_terminal_state():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/sink.py").read_text(encoding="utf-8")
    assert "def _update_deploy_row" in source
    assert "never mutates Deploy.status" in source
    assert 'status__in=(' in source



def test_deployment_consumer_deduplicates_retried_event_ids():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/consumers.py").read_text(encoding="utf-8")
    assert "_seen_event_ids" in source
    assert "_seen_event_order = deque(maxlen=256)" in source
    assert 'event_id = str(payload.get("event_id") or "").strip()' in source



def test_db_success_fences_owner_before_revision_activation():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def activate_revision_and_succeed", 1)[1].split(
        "def transition_deploy_system_terminal", 1
    )[0]
    assert "select_for_update" in method
    assert 'str(deploy.execution_task_id or "") != str(task_id)' in method
    assert "if deploy.cancel_requested" in method
    assert "Service.objects.select_for_update()" in method
    assert "activate_revision_locked(service, revision_id)" in method
    assert '"status": sm.DEPLOY_SUCCEEDED' in method
    assert "DeploymentEventOutbox.objects.create" in method



def test_system_terminal_transition_respects_cancellation_fence():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_deploy_system_terminal", 1)[1].split(
        "def finalize_pending_cancellation", 1
    )[0]
    assert 'if target != sm.DEPLOY_CANCELLED and deploy.cancel_requested:' in method



def test_event_sink_sanitizes_message_before_state_projection():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/sink.py").read_text(encoding="utf-8")
    assert "from deploy.event_pipeline import sanitize" in source
    assert 'message = sanitize(payload.get("message") or "")' in source


def test_outbox_retention_only_prunes_dispatched_rows():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/common/event_outbox.py").read_text(encoding="utf-8")
    method = source.split("def prune_dispatched", 1)[1].split("def _log_db_alias", 1)[0]
    assert "dispatched_at__isnull=False" in method
    assert "dispatched_at__lt=cutoff" in method

def test_outbox_retention_is_scheduled_and_operator_bounded():
    task_source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    settings_source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "config/settings.py").read_text(encoding="utf-8")
    assert "prune_deployment_event_outbox" in task_source
    assert "DEPLOYMENT_EVENT_OUTBOX_RETENTION_DAYS" in task_source
    assert '"schedule": 3600.0' in settings_source


def test_db_success_primitive_updates_service_to_running_atomically():
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def activate_revision_and_succeed", 1)[1].split(
        "def transition_deploy_system_terminal", 1
    )[0]
    assert "sm.check_service_transition" in method
    assert "status=sm.SERVICE_RUNNING" in method
    assert "task_id=None" in method
