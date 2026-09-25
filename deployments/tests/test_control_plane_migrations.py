from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
    assert 'entrypoint: ["/app/entrypoint.sh"]' in web_block
    assert "command:\n      - daphne" in web_block
