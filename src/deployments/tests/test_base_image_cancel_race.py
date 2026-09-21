from pathlib import Path


def test_base_image_build_is_dedicated_task_and_routed():
    tasks = Path("deployments/celery/tasks.py").read_text()
    settings = Path("config/settings.py").read_text()
    assert "build_registered_base_image(base_image_id, task_id=str(self.request.id))" in tasks
    assert '"deployments.celery.tasks.build_base_runtime_image": {"queue": "base-images"}' in settings


def test_force_cancel_releases_base_leases_and_preserves_running_service():
    runtime = Path("services/api/runtime.py").read_text()
    assert "release_base_image_leases(" in runtime
    assert "SERVICE_STATUS_CHOICES.RUNNING if running else SERVICE_STATUS_CHOICES.STOPPED" in runtime


def test_base_runtime_image_has_build_task_ownership_fields():
    models = Path("deploy/models.py").read_text()
    migration_task = Path("deploy/migrations/0012_base_runtime_build_task.py").read_text()
    migration_owner = Path("deploy/migrations/0013_base_runtime_build_owner.py").read_text()
    assert "build_task_id = models.CharField" in models
    assert "build_owner_deployment_id = models.CharField" in models
    assert 'name="build_task_id"' in migration_task
    assert 'name="build_owner_deployment_id"' in migration_owner


def test_force_cancel_does_not_hardcode_service_stopped_state():
    runtime = Path("services/api/runtime.py").read_text()
    assert "fallback_status = SERVICE_STATUS_CHOICES.RUNNING if running else SERVICE_STATUS_CHOICES.STOPPED" in runtime


def test_wait_for_base_build_uses_ready_db_state_before_docker_tag():
    source = Path("deploy/base_images.py").read_text()
    assert 'status == BaseRuntimeImage.Status.READY' in source
    assert 'return _docker_image_exists(image_ref)' in source
    # A Docker tag appearing while BUILDING must not itself release waiters.
    assert 'if _docker_image_exists(image_ref):\n            return True' not in source
