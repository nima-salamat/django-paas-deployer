from pathlib import Path
from django.db.models.deletion import DO_NOTHING


ROOT = Path(__file__).resolve().parents[2]


def test_service_cleanup_covers_external_logs_and_revision_artifacts():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    assert "@receiver(post_delete, sender=Service)" in source
    assert "_cleanup_service_log_records(instance.pk)" in source
    for model_name in (
        "DeployLog",
        "ServiceLogEntry",
        "ServiceLogStream",
        "ServiceLogUsage",
        "LogUsageDaily",
    ):
        assert model_name in source

    assert "@receiver(pre_delete, sender=ServiceRevision)" in source
    assert "artifact.delete(save=False)" in source


def test_service_runtime_cleanup_fails_closed_for_owned_resources():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    assert "Failed to remove Swarm runtime for service" in source
    assert "Refusing to delete service" in source
    assert "Failed to remove application image(s)" in source
    assert "raise" in source.split("def delete_deploy_before_delete_service", 1)[1].split(
        "def _cleanup_service_volumes", 1
    )[0]


def test_private_network_cleanup_checks_explicit_service_attachments():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    assert "ServiceNetworkAttachment.objects.filter(network_id=instance.pk)" in source
    assert "Cannot delete private network" in source
    assert 'labels.get("managed-by") != "django-paas-deployer"' in source


def test_user_signal_does_not_bypass_private_network_ownership_cleanup():
    source = (ROOT / "users" / "signals.py").read_text(encoding="utf-8")

    assert "PrivateNetwork.pre_delete" in source
    assert "DockerNetwork" not in source


def test_deploylog_relations_do_not_cascade_across_database():
    from deploy.models import DeployLog

    assert DeployLog._meta.get_field("service").remote_field.on_delete is DO_NOTHING
    assert DeployLog._meta.get_field("deploy").remote_field.on_delete is DO_NOTHING


def test_service_api_delete_does_not_bypass_signal_ownership_checks():
    source = (ROOT / "services" / "api" / "user_services.py").read_text(encoding="utf-8")

    destroy = source.split("    def destroy(self, request, pk=None", 1)[1].split(
        "    def retrieve(", 1
    )[0]
    assert "_purge_service_runtime(service)" not in destroy
    assert "Service.pre_delete" in destroy


def test_service_delete_reclaims_only_unshared_application_cache_images():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    assert "def _cleanup_service_cache_images(service: Service)" in source
    assert "BuildCacheArtifact.objects.filter(" in source
    assert "BaseRuntimeImage.objects.filter(" in source
    assert "client.containers.list()" in source
    assert "image_ids - other_refs - protected_base_ids - running_ids" in source
    assert "force=False" in source


def test_service_swarm_cleanup_uses_pre_delete_instance():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    handler = source.split(
        "def delete_deploy_before_delete_service", 1
    )[1].split("def _cleanup_service_cache_images", 1)[0]

    assert "SwarmRuntime().remove_service_group(str(instance.pk))" in handler
    assert "service.pk" not in handler
    assert "service.name" not in handler


def test_service_swarm_cleanup_executes_with_signal_instance():
    from types import SimpleNamespace
    from unittest.mock import patch

    from services import signals

    service_id = "3bd97fea-22a7-4c8f-beae-7b7405ad2c74"
    instance = SimpleNamespace(
        pk=service_id,
        name="asdf",
        get_docker_service_name=lambda: "app-3bd97fea-asdf",
        plan=SimpleNamespace(platform="python", plan_type="application"),
        selected_deploy=None,
    )

    with (
        patch.object(signals, "_cancel_active_deployments_for_service"),
        patch.object(signals, "swarm_enabled", return_value=True),
        patch.object(signals, "SwarmRuntime") as runtime_class,
        patch.object(signals, "Container") as container_class,
        patch.object(signals, "Image"),
        patch.object(signals, "_cleanup_service_cache_images"),
        patch.object(signals, "_cleanup_service_volumes"),
    ):
        container_class.return_value.exists.return_value = False

        signals.delete_deploy_before_delete_service(None, instance)

    runtime_class.return_value.remove_service_group.assert_called_once_with(service_id)
