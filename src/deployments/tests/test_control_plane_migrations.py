from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_control_plane_migration_has_one_runtime_owner():
    entrypoint = (ROOT / "entrypoint.sh").read_text()
    compose = (ROOT / "compose.yaml").read_text()

    assert entrypoint.count("python manage.py migrate") == 1
    assert "python manage.py migrate" not in compose
    assert "python manage.py migrate logs --database=deployment_logs" not in compose
    assert "python manage.py setup_deployment_log_db" not in compose

    web_block = compose.split("  web:\n", 1)[1].split(
        "\n  # ============================================================\n  # REDIS",
        1,
    )[0]
    assert 'entrypoint: ["/bin/sh", "/app/entrypoint.sh"]' in web_block
    assert "CODENAME:" not in web_block
    assert "command:\n      - daphne" in web_block


def test_dockerfile_uses_base_image_codename_and_normalizes_linux_mirror():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "ARG CODENAME=" not in dockerfile
    assert 'codename="$${VERSION_CODENAME}"' in dockerfile
    assert 'case "$mirror" in' in dockerfile
    assert '*) mirror="http://$mirror" ;;' in dockerfile



def test_deployment_log_has_no_cross_database_reverse_relations():
    models = (ROOT / "src" / "deploy" / "models.py").read_text(encoding="utf-8")
    deploy_log = models.split("class DeployLog", 1)[1].split("class BuildCacheArtifact", 1)[0]
    assert 'related_name="+"' in deploy_log
    assert "db_constraint=False" in deploy_log
