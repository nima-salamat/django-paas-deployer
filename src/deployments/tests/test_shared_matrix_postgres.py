from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _service_block(compose: str, name: str) -> str:
    start = compose.index(f"  {name}:\n")
    rest = compose[start + len(f"  {name}:\n"):]
    next_service = __import__("re").search(r"\n  [A-Za-z0-9_-]+:\n|\nvolumes:\n|\nnetworks:\n", rest)
    end = start + len(f"  {name}:\n") + (next_service.start() if next_service else len(rest))
    return compose[start:end]


def test_shared_matrix_postgres_mode_is_opt_in_and_keeps_databases_separate():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    overlay = (ROOT / "compose.matrix-postgres.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")

    assert "USE_MATRIX_POSTGRES=0" in env_example
    assert "MATRIX_POSTGRES_MAIN_DB=paas_deployer" in env_example
    assert "MATRIX_POSTGRES_LOG_DB=paas_deployer_logs" in env_example
    assert "matrix-postgres-disabled-in-shared-mode" in overlay
    assert "docker compose -f compose.yaml -f compose.matrix-postgres.yaml" in helper
    assert 'exec docker compose -f compose.yaml "$@"' in helper
    assert "required: false" in compose
    assert "DB_HOST: ${DB_HOST:-db}" in compose
    assert "DEPLOYMENT_LOG_DB_HOST: ${DEPLOYMENT_LOG_DB_HOST:-deployment-log-db}" in compose


def test_all_django_control_plane_containers_join_the_matrix_network():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    for name in (
        "web",
        "celery",
        "deployment-worker",
        "base-image-worker",
        "celery-beat",
        "log-collector",
        "integration-test",
    ):
        block = _service_block(compose, name)
        assert "- matrix-network" in block, name
        assert "DB_NAME: ${DB_NAME:-passdb}" in block, name
        assert "DB_USER: ${DB_USER:-psguser}" in block, name
        assert "DEPLOYMENT_LOG_DB_NAME: ${DEPLOYMENT_LOG_DB_NAME:-deployment_logs}" in block, name


def test_shared_postgres_helper_never_removes_volumes_or_changes_synapse_database():
    helper = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")
    overlay = (ROOT / "compose.matrix-postgres.yaml").read_text(encoding="utf-8")
    docs = (ROOT / "documentation" / "installation.md").read_text(encoding="utf-8")

    assert "docker compose down -v" not in helper
    assert "docker volume rm" not in helper
    assert "paas_deployer_logs" in docs
    assert "Do not" in docs and "synapse" in docs
    assert "docker stop deploy-db deploy-log-db" in docs
