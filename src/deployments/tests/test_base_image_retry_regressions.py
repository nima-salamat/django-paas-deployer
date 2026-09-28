from pathlib import Path

import pytest
from django.utils import timezone

from deploy.models import BaseRuntimeImage, Deploy

ROOT = Path(__file__).resolve().parents[2]


def test_base_image_retry_keeps_record_building_and_preserves_fence_contract():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")
    base = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "status=BaseRuntimeImage.Status.BUILDING" in source
    assert "build_task_id=str(task_id)" in source
    assert 'build_task_id=str(task_id),' in source
    assert "raise self.retry(exc=exc)" in source
    assert "build_started_at = row.build_started_at if continuing_build" in base


def test_terminal_base_image_failure_is_fenced_to_current_owner():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")
    block = source.split("def _mark_base_image_terminal_failure", 1)[1].split("@shared_task", 1)[0]
    assert 'status=BaseRuntimeImage.Status.BUILDING' in block
    assert 'build_task_id=str(task_id)' in block
    assert "if not updated:" in block


def test_base_builder_does_not_terminalize_intermediate_failure():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    block = source.split("def build_registered_base_image", 1)[1].split("def _wait_for_existing_build", 1)[0]
    assert "Celery decides terminal state" in block
    assert 'last_error_details=details' in block
    assert 'status=BaseRuntimeImage.Status.FAILED' not in block


def test_waiter_timeout_is_structured_base_phase_failure():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert 'timeout_phase": "base_image"' in source
    assert "could not become ready within the base-image build/wait limit" in source


def test_pending_renewal_is_preserved_across_retry():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")
    retry = source.split("def _mark_base_image_retry_pending", 1)[1].split("def _mark_base_image_terminal_failure", 1)[0]
    assert "last_error_details" in retry
    assert "details = dict" in retry


def test_retry_pending_is_not_terminalized_by_monitor():
    source = (ROOT / "deployments" / "celery" / "schedules.py").read_text(encoding="utf-8")
    block = source.split("def _reconcile_base_runtime_builds", 1)[1].split("def ", 1)[0]
    assert '"retry_pending"' in block
    assert "continue" in block


def test_phase_deadline_uses_dedicated_timestamps():
    now = timezone.now()
    deployment = Deploy(
        name="phase-clock",
        version=1.0,
        stage="base_image",
        started_at=now - __import__("datetime").timedelta(minutes=15),
        base_image_wait_started_at=now - __import__("datetime").timedelta(minutes=6),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert deadline == deployment.base_image_wait_started_at + __import__("datetime").timedelta(minutes=10)
    assert deadline > now + __import__("datetime").timedelta(minutes=3)


def test_application_phase_gets_full_budget_after_base_ready():
    now = timezone.now()
    deployment = Deploy(
        name="application-clock",
        version=1.0,
        stage="image_build",
        started_at=now - __import__("datetime").timedelta(minutes=13),
        base_image_wait_started_at=now - __import__("datetime").timedelta(minutes=6),
        base_image_ready_at=now - __import__("datetime").timedelta(minutes=7),
        application_started_at=now - __import__("datetime").timedelta(minutes=7),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert int((deadline - now).total_seconds()) == 3 * 60