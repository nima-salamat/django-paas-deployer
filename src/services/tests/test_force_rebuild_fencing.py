"""Regression tests for lifecycle-fenced force rebuild teardown."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.lifecycle import rebuild


ROOT = Path(__file__).resolve().parents[2]


def _service():
    return SimpleNamespace(
        pk="service-123",
        get_docker_service_name=lambda: "app-service-123",
    )


def test_force_rebuild_takes_transaction_lock_and_fences_before_swarm_removal(monkeypatch):
    events = []

    @contextmanager
    def lock(service_id):
        events.append(("lock", service_id))
        yield
        events.append(("unlock", service_id))

    class Runtime:
        def remove_service_group(self, service_id):
            events.append(("remove", service_id))

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(
        rebuild,
        "bump_lifecycle",
        lambda service_id, desired_state: (
            events.append(("fence", service_id, desired_state)) or 17
        ),
    )
    monkeypatch.setattr(rebuild, "swarm_enabled", lambda: True)
    monkeypatch.setattr(rebuild, "SwarmRuntime", Runtime)

    generation, error = rebuild.fence_and_teardown_service_runtime(
        _service(),
        platform="docker",
    )

    assert generation == 17
    assert error is None
    assert events == [
        ("lock", "service-123"),
        ("fence", "service-123", "running"),
        ("remove", "service-123"),
        ("unlock", "service-123"),
    ]


def test_force_rebuild_returns_teardown_error_after_fencing_instead_of_raising(monkeypatch):
    events = []

    @contextmanager
    def lock(service_id):
        events.append("lock")
        yield

    class Runtime:
        def remove_service_group(self, service_id):
            events.append("remove")
            raise RuntimeError("Swarm manager unavailable")

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(
        rebuild,
        "bump_lifecycle",
        lambda service_id, desired_state: (
            events.append("fence") or 23
        ),
    )
    monkeypatch.setattr(rebuild, "swarm_enabled", lambda: True)
    monkeypatch.setattr(rebuild, "SwarmRuntime", Runtime)

    generation, error = rebuild.fence_and_teardown_service_runtime(
        _service(),
        platform="docker",
    )

    assert generation == 23
    assert error == "Swarm manager unavailable"
    assert events == ["lock", "fence", "remove"]


def test_force_rebuild_does_not_teardown_when_lifecycle_lock_is_unavailable(monkeypatch):
    def lock(_service_id):
        raise RuntimeError("service has an active lifecycle operation")

    def unexpected_fence(*_args, **_kwargs):
        raise AssertionError("generation must not be bumped without the lock")

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(rebuild, "bump_lifecycle", unexpected_fence)

    with pytest.raises(RuntimeError, match="active lifecycle operation"):
        rebuild.fence_and_teardown_service_runtime(_service(), platform="docker")


def test_tenant_and_admin_force_rebuild_paths_fail_closed_on_teardown_error():
    runtime_api = (ROOT / "services/api/runtime.py").read_text(encoding="utf-8")
    admin_api = (ROOT / "services/api/admin_services.py").read_text(encoding="utf-8")

    for source in (runtime_api, admin_api):
        assert "fence_and_teardown_service_runtime(" in source
        assert "record_force_rebuild_teardown_failure(" in source
        assert 'if teardown_error is not None:' in source
        assert '"FORCE_REBUILD_TEARDOWN_FAILED"' in source

    assert "start_service force_rebuild teardown warning" not in runtime_api
    assert "start_service force_rebuild teardown warning" not in admin_api


@pytest.mark.django_db
def test_teardown_failure_marks_service_stopped_and_deploy_for_reconciliation():
    from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
    from deploy.models import Deploy, DeploymentStatusChoices
    from plans.models import Plan
    from services.models import PrivateNetwork, Service
    from users.models import User

    user = User.objects.create_user(
        username="force-rebuild-failure",
        email="force-rebuild-failure@example.invalid",
    )
    plan = Plan.objects.create(
        name=NameChoices.BRONZE,
        platform="docker",
        plan_type=PlanTypeChoices.APP,
        max_cpu=1.0,
        max_ram=512,
        max_storage=10,
        price_per_hour=0,
        storage_type=StorageTypeChoices.SSD,
    )
    network = PrivateNetwork.objects.create(
        name="force-rebuild-failure-network",
        user=user,
    )
    service = Service.objects.create(
        name="force-rebuild-failure-service",
        user=user,
        plan=plan,
        network=network,
        status="running",
        desired_state="running",
    )
    Service.objects.filter(pk=service.pk).update(lifecycle_generation=8)
    deploy = Deploy.objects.create(
        name="force-rebuild-failure-deploy",
        service=service,
        created_by=user,
        status=DeploymentStatusChoices.SUCCEEDED,
    )

    rebuild.record_force_rebuild_teardown_failure(
        service.pk,
        deploy.pk,
        expected_generation=8,
        error="Swarm removal timed out",
    )

    service.refresh_from_db()
    deploy.refresh_from_db()
    assert service.status == "failed"
    assert service.desired_state == "stopped"
    assert service.task_id in (None, "")
    assert deploy.reconciliation_required is True
    assert deploy.cleanup_status == "pending"
    assert deploy.cleanup_failures == [
        "Force-rebuild teardown failed: Swarm removal timed out"
    ]


@pytest.mark.django_db
def test_new_deploy_captures_ready_app_lifecycle_generation_and_active_revision():
    from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
    from deploy.models import Deploy
    from plans.models import Plan
    from services.models import PrivateNetwork, Service, ServiceRevision
    from users.models import User

    user = User.objects.create_user(
        username="ready-app-generation-capture",
        email="ready-app-generation-capture@example.invalid",
    )
    plan = Plan.objects.create(
        name=NameChoices.BRONZE,
        platform="docker",
        plan_type=PlanTypeChoices.APP,
        max_cpu=1.0,
        max_ram=512,
        max_storage=10,
        price_per_hour=0,
        storage_type=StorageTypeChoices.SSD,
    )
    network = PrivateNetwork.objects.create(
        name="ready-app-generation-network",
        user=user,
    )
    service = Service.objects.create(
        name="ready-app-generation-service",
        user=user,
        plan=plan,
        network=network,
        status="stopped",
        desired_state="stopped",
    )
    Service.objects.filter(pk=service.pk).update(lifecycle_generation=31)
    revision = ServiceRevision.objects.create(
        service=service,
        revision_number=1,
        config_snapshot={},
    )
    Service.objects.filter(pk=service.pk).update(active_revision=revision)
    service.refresh_from_db(fields=["lifecycle_generation", "active_revision"])

    deploy = Deploy.objects.create(
        name="ready-app-generation-deploy",
        service=service,
        created_by=user,
    )

    assert deploy.expected_lifecycle_generation == 31
    assert deploy.expected_active_revision_id == str(revision.pk)
