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
    assert "release_application_image_references" in source


def test_cache_cleanup_reads_container_image_id_without_inspecting_image():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from services import signals

    class ContainerWithMissingImage:
        attrs = {"Image": "sha256:missing"}

        @property
        def image(self):
            raise AssertionError("cache cleanup must not inspect a possibly missing image")

    first_qs = MagicMock()
    first_qs.values_list.return_value = [("sha256:missing", "cache-ref")]
    second_qs = MagicMock()
    second_qs.exclude.return_value.values_list.return_value = []
    base_qs = MagicMock()
    base_qs.values_list.return_value = []

    artifact_manager = MagicMock()
    artifact_manager.filter.side_effect = [first_qs, second_qs]
    base_manager = MagicMock()
    base_manager.filter.return_value = base_qs

    client = SimpleNamespace(
        containers=SimpleNamespace(list=MagicMock(return_value=[ContainerWithMissingImage()])),
        images=SimpleNamespace(remove=MagicMock()),
    )
    service = SimpleNamespace(pk="svc-1", name="wordpress")

    with (
        patch("deploy.build_cache.BuildCacheArtifact.objects", artifact_manager),
        patch("deploy.models.BaseRuntimeImage.objects", base_manager),
        patch("deployments.core.manager.client_manager.get_docker_client", return_value=client),
    ):
        signals._cleanup_service_cache_images(service)

    client.images.remove.assert_not_called()


def test_service_swarm_cleanup_uses_pre_delete_instance():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    helper = source.split("def cleanup_service_resources", 1)[1].split(
        "@receiver(pre_delete, sender=Service)", 1
    )[0]

    assert "SwarmRuntime().remove_service_group(str(service.pk))" in helper
    assert "def delete_deploy_before_delete_service" in source
    assert "cleanup_service_resources(instance)" in source


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



def test_service_cleanup_recovers_owned_stale_volume_attachments():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")
    assert "volume is in use" in source
    assert 'client.containers.list(all=True, filters={"volume": docker_name})' in source
    assert 'labels.get("passdeployer.service")' in source
    assert "raw.remove(force=True)" in source
    assert "for attempt in range(5)" in source
    assert "never force-delete an attached volume" in source or "never force-delete an attached volume" in source.lower()


def test_ready_app_delete_preflights_all_child_resources_before_deleting_rows():
    source = (ROOT / "app_catalog" / "apis.py").read_text(encoding="utf-8")
    delete_section = source.split("class ApplicationInstanceDetailAPIView", 1)[1].split(
        "class ApplicationInstanceCancelAPIView", 1
    )[0]
    assert "cleanup_service_resources" in delete_section
    assert "for row in service_rows:" in delete_section
    assert "application_cleanup_pending" in delete_section



def test_legacy_catalog_volume_wins_over_stale_unowned_canonical_shadow():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from services import signals

    service_id = "8e572596-a3d4-4025-9d0e-16e938395c52"
    legacy_name = "cat-8e572596-wordpress-files"
    canonical_name = "vol-12345678-wordpress-files"

    registry_volume = SimpleNamespace(
        pk="vol-row-1",
        name=legacy_name,
        service_id=service_id,
        get_docker_volume_name=lambda: canonical_name,
        delete=MagicMock(),
    )
    service = SimpleNamespace(pk=service_id, name="blog-wordpress-docker")

    canonical_raw = SimpleNamespace(attrs={"Labels": {}})
    legacy_raw = SimpleNamespace(attrs={"Labels": {}})
    probes = {}

    def docker_volume(name):
        probe = SimpleNamespace(client=SimpleNamespace(volumes=SimpleNamespace(get=MagicMock())))
        if name == canonical_name:
            probe.client.volumes.get.return_value = canonical_raw
        elif name == legacy_name:
            probe.client.volumes.get.return_value = legacy_raw
        else:
            raise AssertionError(f"unexpected Docker volume lookup: {name}")
        probes[name] = probe
        return probe

    volumes_qs = MagicMock()
    volumes_qs.__iter__.return_value = iter([registry_volume])

    with (
        patch.object(signals.Volume.objects, "filter", return_value=volumes_qs),
        patch.object(signals, "DockerVolume", side_effect=docker_volume),
        patch.object(signals, "_remove_owned_docker_volume") as remove_owned,
    ):
        signals._cleanup_service_volumes(service)

    remove_owned.assert_called_once()
    assert remove_owned.call_args.args[2] == legacy_name
    registry_volume.delete.assert_called_once_with()


def test_legacy_catalog_volume_falls_back_to_unlabeled_canonical_identity_when_legacy_is_absent():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from services import signals

    service_id = "8e572596-a3d4-4025-9d0e-16e938395c52"
    legacy_name = "cat-8e572596-wordpress-files"
    canonical_name = "vol-12345678-wordpress-files"

    registry_volume = SimpleNamespace(
        pk="vol-row-1",
        name=legacy_name,
        service_id=service_id,
        get_docker_volume_name=lambda: canonical_name,
        delete=MagicMock(),
    )
    service = SimpleNamespace(pk=service_id, name="blog-wordpress-docker")

    canonical_raw = SimpleNamespace(attrs={"Labels": {}})

    def docker_volume(name):
        assert name == canonical_name
        return SimpleNamespace(
            client=SimpleNamespace(
                volumes=SimpleNamespace(get=MagicMock(return_value=canonical_raw))
            )
        )

    volumes_qs = MagicMock()
    volumes_qs.__iter__.return_value = iter([registry_volume])

    with (
        patch.object(signals.Volume.objects, "filter", return_value=volumes_qs),
        patch.object(signals, "DockerVolume", side_effect=docker_volume),
        patch.object(signals, "_remove_owned_docker_volume") as remove_owned,
    ):
        signals._cleanup_service_volumes(service)

    remove_owned.assert_called_once()
    assert remove_owned.call_args.args[2] == canonical_name
    assert registry_volume._docker_cleanup_completed is True
    registry_volume.delete.assert_called_once_with()


def test_volume_pre_delete_skips_when_parent_cleanup_already_removed_docker_volume():
    from types import SimpleNamespace
    from unittest.mock import patch

    from services import signals

    instance = SimpleNamespace(
        name="cat-8e572596-wordpress-files",
        _docker_cleanup_completed=True,
    )

    with patch.object(signals, "DockerVolume") as docker_volume:
        signals.cleanup_volume_on_delete(None, instance)

    docker_volume.assert_not_called()


def test_in_use_managed_volume_cleanup_removes_owned_task_container_then_retries():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from services import signals

    class VolumeInUseError(Exception):
        pass

    service = SimpleNamespace(pk="svc-1", name="mariadb")
    attached = SimpleNamespace(
        id="task-container-1",
        name="app-svc-1-mariadb",
        status="running",
        labels={"managed-by": "django-paas-deployer", "passdeployer.service": "svc-1"},
    )
    attached.reload = Mock()
    attached.stop = Mock()
    attached.remove = Mock()

    client = SimpleNamespace(
        containers=SimpleNamespace(
            list=Mock(return_value=[attached]),
        )
    )

    docker_volume = SimpleNamespace(client=client)
    remove_calls = {"count": 0}

    def remove_volume():
        remove_calls["count"] += 1
        if remove_calls["count"] == 1:
            raise VolumeInUseError("409 Conflict: volume is in use")
        return True

    docker_volume.remove = remove_volume

    signals._remove_owned_docker_volume(service, docker_volume, "cat-mariadb")

    assert remove_calls["count"] == 2
    attached.stop.assert_called_once_with(timeout=10)
    attached.remove.assert_called_once_with(force=True)




def test_cache_cleanup_releases_owned_tag_without_force_deleting_shared_image():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from services import signals

    class FakeImage:
        id = "sha256:" + "a" * 64
        def __init__(self, tags):
            self.tags = list(tags)
            self.attrs = {
                "RepoTags": list(tags),
                "Config": {"Labels": {"io.passdeployer.service": "svc-1"}},
            }

    image = FakeImage(["app-svc-1:1", "shared/image:1"])
    removed = []

    class Images:
        def get(self, ref):
            if ref == image.id or ref in image.tags:
                return image
            from docker.errors import ImageNotFound
            raise ImageNotFound(ref)

        def remove(self, ref, force=False):
            assert force is False
            removed.append(ref)
            if ref in image.tags:
                image.tags.remove(ref)
                image.attrs["RepoTags"] = list(image.tags)
            else:
                if ref == image.id:
                    image.tags.clear()
                    image.attrs["RepoTags"] = []

    first_qs = MagicMock()
    first_qs.values_list.return_value = [(image.id, "app-svc-1:1")]
    second_qs = MagicMock()
    second_qs.exclude.return_value.values_list.return_value = []
    base_qs = MagicMock()
    base_qs.values_list.return_value = []
    artifact_manager = MagicMock()
    artifact_manager.filter.side_effect = [first_qs, second_qs]
    base_manager = MagicMock()
    base_manager.filter.return_value = base_qs
    client = SimpleNamespace(
        containers=SimpleNamespace(list=MagicMock(return_value=[])),
        images=Images(),
    )
    service = SimpleNamespace(pk="svc-1", name="wordpress")

    with (
        patch("deploy.build_cache.BuildCacheArtifact.objects", artifact_manager),
        patch("deploy.models.BaseRuntimeImage.objects", base_manager),
        patch("deployments.core.manager.client_manager.get_docker_client", return_value=client),
    ):
        signals._cleanup_service_cache_images(service)

    assert removed == ["app-svc-1:1"]
    assert image.tags == ["shared/image:1"]


def test_release_application_image_rejects_unknown_shared_reference_ownership():
    from types import SimpleNamespace
    from docker.errors import ImageNotFound
    from deploy.build_cache import release_application_image_references

    class Images:
        def get(self, ref):
            if ref == "sha256:" + "b" * 64:
                return SimpleNamespace(
                    id=ref,
                    tags=["foreign:1", "foreign:2"],
                    attrs={"RepoTags": ["foreign:1", "foreign:2"], "Config": {"Labels": {}}},
                )
            raise ImageNotFound(ref)

        def remove(self, ref, force=False):
            raise AssertionError("unknown shared references must not be removed")

    client = SimpleNamespace(images=Images())
    ok, detail = release_application_image_references(
        "sha256:" + "b" * 64,
        ["not-the-image:1"],
        owner_service_ids=("svc-1",),
        client=client,
    )

    assert ok is False
    assert "none could be proven" in detail


def test_precleaned_service_delete_skips_duplicate_runtime_cleanup():
    source = (ROOT / "services" / "signals.py").read_text(encoding="utf-8")

    assert "def delete_service_row_after_cleanup(service: Service)" in source
    assert 'setattr(service, "_docker_cleanup_completed", True)' in source
    signal = source.split("@receiver(pre_delete, sender=Service)", 1)[1].split(
        "def _cleanup_service_volumes", 1
    )[0]
    assert 'getattr(instance, "_docker_cleanup_completed", False)' in signal
