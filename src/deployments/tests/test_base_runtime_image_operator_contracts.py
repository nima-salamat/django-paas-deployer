from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import timezone

from deploy.base_images import BaseImageSpec, _php, _spec_for_record, deployment_phase_remaining_seconds, make_specs
from deploy.models import BaseRuntimeImage, Deploy


ROOT = Path(__file__).resolve().parents[2]


def _config(platform, runtime_version="8.4", frontend_root=None):
    return SimpleNamespace(platform=platform, runtime_version=runtime_version, frontend_root=frontend_root)


def test_php_base_identity_is_canonical_and_variant_is_stable():
    spec = _php("8.4")
    assert spec.image_ref == "paas-base/php-apache:8.4-r1"
    assert spec.variant == "apache"
    assert spec.repository == "paas-base/php-apache"
    assert "/var/www/html/public" not in spec.dockerfile
    assert "APACHE_DOCUMENT_ROOT" not in spec.dockerfile


def test_plain_php_and_framework_php_share_the_same_base_identity():
    plain = make_specs(_config("php"))[0]
    laravel = make_specs(_config("laravel", frontend_root="resources/js"))[0]
    assert plain.image_ref == "paas-base/php-apache:8.4-r1"
    assert laravel.image_ref == plain.image_ref
    assert plain.variant == laravel.variant == "apache"


def test_supported_non_php_base_names_remain_stable():
    node = make_specs(_config("nodejs", runtime_version="20"))[0]
    python = make_specs(_config("python", runtime_version="3.11"))[0]
    nginx = make_specs(_config("static"))[0]
    go = make_specs(_config("go", runtime_version="1.21"))[0]
    assert node.image_ref == "paas-base/node-alpine:20-r1"
    assert python.image_ref == "paas-base/python-slim:3.11-r1"
    assert nginx.image_ref == "paas-base/nginx:alpine-r1"
    assert go.image_ref == "paas-base/go-alpine:1.21-r1"


def test_php_registry_identity_includes_variant_and_host():
    fields = None
    for constraint in BaseRuntimeImage._meta.constraints:
        if constraint.name == "uniq_base_runtime_image_host":
            fields = tuple(constraint.fields)
            break
    assert fields == ("logical_runtime", "runtime_version", "variant", "architecture", "docker_host")


def test_legacy_php_registry_rows_resolve_to_the_canonical_definition():
    root_row = BaseRuntimeImage(logical_runtime="php", runtime_version="8.4", variant="apache-root")
    public_row = BaseRuntimeImage(logical_runtime="php", runtime_version="8.4", variant="apache-public")
    assert _spec_for_record(root_row).image_ref == "paas-base/php-apache:8.4-r1"
    assert _spec_for_record(public_row).image_ref == "paas-base/php-apache:8.4-r1"



def test_legacy_php_builder_persists_canonical_identity_fields():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    block = source.split("def build_registered_base_image", 1)[1].split("def _wait_for_existing_build", 1)[0]
    assert "legacy_php_identity" in block
    assert '"variant", "source_image", "image_repository", "image_tag", "image_ref"' in block
def test_php_definition_fingerprint_is_shared_by_canonical_and_legacy_rows():
    from deploy.base_images import _spec_fingerprint
    canonical = _php("8.4")
    assert _spec_fingerprint(canonical) == _spec_fingerprint(
        _spec_for_record(
            BaseRuntimeImage(logical_runtime="php", runtime_version="8.4", variant="apache-root")
        )
    )


def test_phase_deadline_uses_base_wait_start_not_deployment_start():
    now = timezone.now()
    deployment = Deploy(
        name="phase-clock",
        version=1.0,
        stage="base_image",
        started_at=now - timedelta(minutes=15),
        base_image_wait_started_at=now - timedelta(minutes=6),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert deadline == deployment.base_image_wait_started_at + timedelta(minutes=10)
    assert deadline > now + timedelta(minutes=3)


def test_application_phase_gets_a_fresh_budget_after_base_readiness():
    now = timezone.now()
    deployment = Deploy(
        name="phase-clock-app",
        version=1.0,
        stage="image_build",
        started_at=now - timedelta(minutes=15),
        base_image_wait_started_at=now - timedelta(minutes=6),
        base_image_ready_at=now - timedelta(minutes=9),
        application_started_at=now - timedelta(minutes=7),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert deadline == deployment.application_started_at + timedelta(minutes=10)
    assert deadline > now + timedelta(minutes=2)





def test_exhausted_base_phase_timeout_is_not_retried():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")
    block = source.split("@shared_task(bind=True, max_retries=2, default_retry_delay=10)", 1)[1].split("# ===========================================================================", 1)[0]
    assert "isinstance(exc, TimeoutError)" in block
    assert "raise self.retry(exc=exc)" in block
    timeout_pos = block.index("isinstance(exc, TimeoutError)")
    retry_pos = block.index("raise self.retry(exc=exc)")
    assert timeout_pos < retry_pos
def test_base_builder_checks_the_same_ten_minute_budget_during_execution():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "base_image_build_timeout_minutes() * 60" in source
    assert "Base-image build exceeded the dedicated" in source
    assert '"build_task_id", "build_started_at"' in source


def test_pending_definition_is_requeued_after_active_base_build_finishes():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    block = source.split("def build_registered_base_image", 1)[1].split("def _wait_for_existing_build", 1)[0]
    assert 'pending_definition = (' in block
    assert 'row.status = BaseRuntimeImage.Status.PENDING' in block
    assert 'request_base_runtime_image_build(' in block
    assert '"pending_definition_fingerprint"' in block


def test_manual_build_and_renew_use_the_same_request_path():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    request_block = source.split("def request_base_runtime_image_build", 1)[1].split("def build_registered_base_image", 1)[0]
    assert "build_base_runtime_image.apply_async" in request_block
    assert 'kwargs={"force_rebuild": requested_force' in request_block
def test_phase_timeout_examples_match_10_plus_10_contract():
    now = timezone.now()

    base = Deploy(
        name="base-6m-app-7m",
        version=1.0,
        stage="base_image",
        started_at=now - timedelta(minutes=13),
        base_image_wait_started_at=now - timedelta(minutes=6),
    )
    assert deployment_phase_remaining_seconds(base, now=now) == 4 * 60

    application = Deploy(
        name="base-ready-app-7m",
        version=1.0,
        stage="image_build",
        started_at=now - timedelta(minutes=13),
        base_image_wait_started_at=now - timedelta(minutes=6),
        base_image_ready_at=now - timedelta(minutes=7),
        application_started_at=now - timedelta(minutes=7),
    )
    assert deployment_phase_remaining_seconds(application, now=now) == 3 * 60


def test_base_phase_times_out_after_10_minutes_independent_of_old_deploy_start():
    now = timezone.now()
    deployment = Deploy(
        name="base-11m",
        version=1.0,
        stage="base_image",
        started_at=now - timedelta(minutes=20),
        base_image_wait_started_at=now - timedelta(minutes=11),
    )
    assert deployment_phase_remaining_seconds(deployment, now=now) == 0


def test_application_phase_times_out_after_10_minutes_from_application_start():
    now = timezone.now()
    deployment = Deploy(
        name="app-11m",
        version=1.0,
        stage="image_build",
        started_at=now - timedelta(minutes=20),
        base_image_wait_started_at=now - timedelta(minutes=5),
        base_image_ready_at=now - timedelta(minutes=11),
        application_started_at=now - timedelta(minutes=11),
    )
    assert deployment_phase_remaining_seconds(deployment, now=now) == 0


def test_phase_remaining_contract_is_shared_by_base_wait_helper():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "deployment_phase_remaining_seconds(deployment_id)" in source
    assert "base_image_build_timeout_minutes" in source
    assert "values_list(\"started_at\"" not in source


def test_base_wait_event_explains_shared_builder_and_records_owner():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "waiting_for_existing_build" in source
    assert "owner_task_id" in source
    assert "build_started_at" in source
    assert "Waiting for the shared build to complete." in source


def test_operator_base_image_actions_route_through_one_request_helper():
    admin_source = (ROOT / "deploy" / "admin.py").read_text(encoding="utf-8")
    view_source = (ROOT / "deploy" / "wagtail_admin" / "views.py").read_text(encoding="utf-8")
    assert "request_base_runtime_image_build" in admin_source
    assert "build_base_runtime_image.apply_async" not in admin_source.split("class BaseRuntimeImageAdmin", 1)[1]
    assert "request_base_runtime_image_build" in view_source
    assert "client.api.build" not in view_source


def test_wagtail_exposes_build_and_renew_listing_controls_with_operator_permission():
    source = (ROOT / "deploy" / "wagtail_hooks.py").read_text(encoding="utf-8")
    assert 'register_snippet_listing_buttons' in source
    assert 'Build / Ensure available' in source
    assert 'Renew / Rebuild' in source
    assert 'change_baseruntimeimage' in source


def test_wagtail_base_image_identity_fields_are_not_operator_editable():
    source = (ROOT / "deploy" / "wagtail_admin" / "models.py").read_text(encoding="utf-8")
    editable = source.split("class BaseRuntimeImageViewSet", 1)[1].split("class SwarmInfrastructurePermissionPolicy", 1)[0]
    assert 'editable=["enabled", "auto_build"]' in editable
    assert '"logical_runtime", "runtime_version", "variant", "architecture"' in editable


def test_manual_renew_while_building_sets_rebuild_requested_without_replacing_owner():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    block = source.split("def request_base_runtime_image_build", 1)[1].split("def build_registered_base_image", 1)[0]
    assert 'if row.status == BaseRuntimeImage.Status.BUILDING:' in block
    assert 'row.rebuild_requested = True' in block
    assert 'row.build_task_id' in block
    assert 'coalesced' in block


def test_base_builder_preserves_original_build_started_at_across_retries():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "build_started_at = row.build_started_at or timezone.now()" in source
    assert "row.build_started_at = build_started_at" in source


def test_base_retry_and_terminal_helpers_are_fenced_by_task_id():
    source = (ROOT / "deployments" / "celery" / "tasks.py").read_text(encoding="utf-8")
    retry_block = source.split("def _mark_base_image_retry_pending", 1)[1].split("def _mark_base_image_terminal_failure", 1)[0]
    terminal_block = source.split("def _mark_base_image_terminal_failure", 1)[1].split("@shared_task(bind=True, max_retries=2, default_retry_delay=10)", 1)[0]
    assert 'build_task_id=str(task_id)' in retry_block
    assert 'build_task_id=str(task_id)' in terminal_block


def test_monitor_base_image_timeout_uses_dedicated_policy_key():
    source = (ROOT / "deployments" / "celery" / "schedules.py").read_text(encoding="utf-8")
    block = source.split("def _reconcile_base_runtime_builds", 1)[1].split("def ", 1)[0]
    assert 'policies["base_image_build_timeout_minutes"]' in block
    assert "BaseImageTimeout" in block


def test_base_runtime_timeout_setting_is_dedicated_and_legacy_name_is_alias_only():
    source = (ROOT / "core" / "settings_service.py").read_text(encoding="utf-8")
    assert "def base_image_build_timeout_minutes()" in source
    assert 'base_image_build_timeout_minutes' in source
    assert 'def monitor_stale_base_build_minutes()' in source
    assert 'return base_image_build_timeout_minutes()' in source

def test_legacy_php_rows_are_converged_by_manual_build_request():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    block = source.split("def request_base_runtime_image_build", 1)[1].split("def build_registered_base_image", 1)[0]
    assert 'row.variant = "apache"' in block
    assert 'row.image_repository = _php(str(row.runtime_version)).repository' in block


def test_legacy_php_identity_migration_is_ordered_after_phase_timestamp_migration():
    migration = (ROOT / "deploy" / "migrations" / "0023_canonical_php_base_runtime_identity.py").read_text(encoding="utf-8")
    assert '"0022_deploy_base_image_phase_timestamps"' in migration
    assert '"apache-root", "apache-public"' in migration
    assert "safe_to_remove" in migration


