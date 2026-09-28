from pathlib import Path
from types import SimpleNamespace

from django.utils import timezone

from deploy.base_images import BaseImageSpec, _php, _spec_fingerprint, make_specs
from deploy.models import BaseRuntimeImage, Deploy


ROOT = Path(__file__).resolve().parents[2]


def _config(platform, runtime_version="8.4", frontend_root=None):
    return SimpleNamespace(
        platform=platform,
        runtime_version=runtime_version,
        frontend_root=frontend_root,
    )


def test_php_base_identity_is_canonical():
    spec = _php("8.4")
    assert spec.image_ref == "paas-base/php-apache:8.4-r1"
    assert spec.variant == "apache"
    assert spec.repository == "paas-base/php-apache"
    assert "APACHE_DOCUMENT_ROOT" not in spec.dockerfile
    assert "/var/www/html/public" not in spec.dockerfile


def test_plain_php_and_laravel_share_one_php_base_identity():
    plain = make_specs(_config("php"))[0]
    laravel = make_specs(_config("laravel", frontend_root="resources/js"))[0]
    assert plain.image_ref == "paas-base/php-apache:8.4-r1"
    assert laravel.image_ref == plain.image_ref
    assert plain.variant == laravel.variant == "apache"


def test_other_base_image_names_remain_stable():
    assert make_specs(_config("nodejs", "20"))[0].image_ref == "paas-base/node-alpine:20-r1"
    assert make_specs(_config("python", "3.11"))[0].image_ref == "paas-base/python-slim:3.11-r1"
    assert make_specs(_config("static"))[0].image_ref == "paas-base/nginx:alpine-r1"
    assert make_specs(_config("go", "1.21"))[0].image_ref == "paas-base/go-alpine:1.21-r1"


def test_php_document_root_is_application_layer_not_base_definition():
    source = (ROOT / "deployments" / "core" / "dockerfile.py").read_text(encoding="utf-8")
    assert "def _apply_php_document_root" in source
    assert "def _php(version: str)" in (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")


def test_canonical_php_fingerprint_changes_when_definition_changes():
    canonical = _php("8.4")
    changed = BaseImageSpec(
        canonical.logical_runtime, canonical.version, canonical.variant,
        canonical.source_image, canonical.repository, canonical.tag,
        canonical.dockerfile + "\n# operator change\n",
    )
    assert _spec_fingerprint(canonical) != _spec_fingerprint(changed)


def test_registry_identity_still_includes_variant_and_host():
    fields = None
    for constraint in BaseRuntimeImage._meta.constraints:
        if constraint.name == "uniq_base_runtime_image_host":
            fields = tuple(constraint.fields)
            break
    assert fields == ("logical_runtime", "runtime_version", "variant", "architecture", "docker_host")


def test_legacy_php_rows_are_preserved_as_legacy_definitions_for_safety():
    root_row = BaseRuntimeImage(logical_runtime="php", runtime_version="8.4", variant="apache-root")
    public_row = BaseRuntimeImage(logical_runtime="php", runtime_version="8.4", variant="apache-public")
    from deploy.base_images import _spec_for_record
    assert _spec_for_record(root_row).image_ref == "paas-base/php-apache-root:8.4-r1"
    assert _spec_for_record(public_row).image_ref == "paas-base/php-apache:8.4-r1"


def test_phase_deadline_uses_base_wait_started_timestamp():
    from datetime import timedelta
    now = timezone.now()
    deployment = Deploy(
        name="base-phase",
        version=1.0,
        stage="base_image",
        started_at=now - timedelta(minutes=15),
        base_image_wait_started_at=now - timedelta(minutes=6),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert deadline == deployment.base_image_wait_started_at + timedelta(minutes=10)


def test_application_phase_deadline_is_fresh_after_base_ready():
    from datetime import timedelta
    now = timezone.now()
    deployment = Deploy(
        name="app-phase",
        version=1.0,
        stage="image_build",
        started_at=now - timedelta(minutes=13),
        base_image_ready_at=now - timedelta(minutes=7),
        application_started_at=now - timedelta(minutes=7),
    )
    deadline = deployment.lifecycle_phase_deadline(
        base_timeout_minutes=10, application_timeout_minutes=10, now=now
    )
    assert int((deadline - now).total_seconds()) == 3 * 60


def test_manual_and_automatic_operator_builds_share_one_request_helper():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "def request_base_runtime_image_build" in source
    request_block = source.split("def request_base_runtime_image_build", 1)[1].split("def build_registered_base_image", 1)[0]
    assert "build_base_runtime_image.apply_async" in request_block
    assert 'kwargs={"force_rebuild": requested_force' in request_block
    assert "client.api.build" not in request_block


def test_wagtail_base_image_controls_use_operator_permission_and_request_helper():
    hooks = (ROOT / "deploy" / "wagtail_hooks.py").read_text(encoding="utf-8")
    views = (ROOT / "deploy" / "wagtail_admin" / "views.py").read_text(encoding="utf-8")
    assert "register_snippet_listing_buttons" in hooks
    assert "Build / Ensure available" in hooks
    assert "Renew / Rebuild" in hooks
    assert "change_baseruntimeimage" in hooks
    assert "request_base_runtime_image_build" in views
    assert "client.api.build" not in views


def test_wagtail_identity_fields_are_not_editable():
    source = (ROOT / "deploy" / "wagtail_admin" / "models.py").read_text(encoding="utf-8")
    block = source.split("class BaseRuntimeImageViewSet", 1)[1].split("class SwarmInfrastructurePermissionPolicy", 1)[0]
    assert 'editable=["enabled", "auto_build"]' in block
    assert '"logical_runtime", "runtime_version", "variant", "architecture"' in block


def test_timeout_contract_is_dedicated_to_base_images():
    source = (ROOT / "core" / "settings_service.py").read_text(encoding="utf-8")
    assert "def base_image_build_timeout_minutes()" in source
    assert '"base_image_build_timeout_minutes"' in source
    assert "def base_image_timeout_minutes()" in source
    assert "return base_image_build_timeout_minutes()" in source


def test_monitor_uses_phase_deadline_instead_of_deploy_started_at():
    source = (ROOT / "deployments" / "celery" / "schedules.py").read_text(encoding="utf-8")
    assert "deployment_phase_remaining_seconds" in source
    assert 'policies["base_image_timeout_minutes"]' not in source


def test_base_wait_logs_shared_builder_identity():
    source = (ROOT / "deploy" / "base_images.py").read_text(encoding="utf-8")
    assert "Waiting for the shared build to complete." in source
    assert "waiting_for_existing_build" in source
    assert "owner_task_id" in source


def test_migration_handles_legacy_php_rows_without_deleting_docker_images():
    migration = (ROOT / "deploy" / "migrations" / "0023_canonical_php_base_runtime_identity.py").read_text(encoding="utf-8")
    assert "LEGACY_VARIANTS" in migration
    assert "docker_image_preserved" in migration
    assert "safe_to_remove_after_release" in migration
    assert "BaseRuntimeImageLease" in migration

def test_active_base_build_coalesces_repeated_renew_requests(monkeypatch):,    import deploy.base_images as base_images,,    class FakeAtomic:,        def __enter__(self):,            return self,        def __exit__(self, exc_type, exc, tb):,            return False,,    class FakeManager:,        def select_for_update(self):,            return self,        def get(self, pk):,            return row,,    class FakeRow:,        pk = "base-1",        enabled = True,        logical_runtime = "node",        runtime_version = "20",        variant = "alpine",        architecture = "",        docker_host = "daemon-1",        status = BaseRuntimeImage.Status.BUILDING,        build_task_id = "owner-task",        rebuild_requested = False,        rebuild_requested_at = None,        definition_fingerprint = "fp",        image_ref = "paas-base/node-alpine:20-r1",        def save(self, **kwargs):,            return None,,    row = FakeRow(),    monkeypatch.setattr(base_images.BaseRuntimeImage, "objects", FakeManager()),    monkeypatch.setattr(base_images.transaction, "atomic", lambda: FakeAtomic()),    result = base_images.request_base_runtime_image_build(row.pk, force_rebuild=True),    assert result["coalesced"] is True,    assert result["waiting"] is True,    assert result["rebuild_requested"] is True,    assert row.build_task_id == "owner-task",    assert row.status == BaseRuntimeImage.Status.BUILDING,
def test_wagtail_listing_hook_returns_build_and_renew_for_operator():
    from deploy.wagtail_hooks import base_runtime_image_listing_buttons

    class User:
        is_staff = True
        is_superuser = False
        def has_perm(self, name):
            return name == "deploy.change_baseruntimeimage"

    row = BaseRuntimeImage(
        logical_runtime="php", runtime_version="8.4", variant="apache",
        architecture="", docker_host="test-daemon",
        source_image="docker.io/php:8.4-apache",
        image_repository="paas-base/php-apache", image_tag="8.4-r1",
        image_ref="paas-base/php-apache:8.4-r1",
    )
    buttons = list(base_runtime_image_listing_buttons(row, User(), "/admin/snippets/deploy/base-runtime-images/"))
    labels = [button.label for button in buttons]
    assert labels == ["Build / Ensure available", "Renew / Rebuild"]


def test_wagtail_listing_hook_hides_infrastructure_actions_from_non_operator():
    from deploy.wagtail_hooks import base_runtime_image_listing_buttons

    class User:
        is_staff = False
        is_superuser = False
        def has_perm(self, name):
            return False

    row = BaseRuntimeImage(
        logical_runtime="php", runtime_version="8.4", variant="apache",
        architecture="", docker_host="test-daemon",
        source_image="docker.io/php:8.4-apache",
        image_repository="paas-base/php-apache", image_tag="8.4-r1",
        image_ref="paas-base/php-apache:8.4-r1",
    )
    assert list(base_runtime_image_listing_buttons(row, User())) == []