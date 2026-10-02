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
