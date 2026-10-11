from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_orphan_image_cleanup_is_dry_run_by_default_and_requires_proven_ownership():
    source = (
        ROOT
        / "src"
        / "deploy"
        / "management"
        / "commands"
        / "cleanup_orphaned_application_images.py"
    ).read_text(encoding="utf-8")

    assert '"--apply"' in source
    assert 'apply_changes = bool(options["apply"])' in source
    assert 'if not apply_changes:' in source
    assert "io.passdeployer.service" in source
    assert "io.passdeployer.deployment" in source
    assert "BaseRuntimeImage.objects" in source
    assert "client.containers.list(all=True)" in source
    assert "client.services.list()" in source
    assert "release_application_image_references(" in source
    assert "Unlabelled historical images are left for manual review." in source


def test_service_image_reference_classifier_only_accepts_canonical_app_repositories():
    from deploy.build_cache import is_platform_application_image_ref

    assert is_platform_application_image_ref("app-1234-wordpress:1.00-rabcdef012345")
    assert is_platform_application_image_ref("registry.example.test:5000/app-1234-wordpress:1.00")
    assert not is_platform_application_image_ref("shared/cache:1")
    assert not is_platform_application_image_ref("postgres:18")
