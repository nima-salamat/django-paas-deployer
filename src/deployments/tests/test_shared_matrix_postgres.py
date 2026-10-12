from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]


def _service_block(compose: str, name: str) -> str:
    start = compose.index(f"  {name}:\n")
    rest = compose[start + len(f"  {name}:\n"):]
    next_service = re.search(r"\n  [A-Za-z0-9_-]+:\n|\nvolumes:\n|\nnetworks:\n", rest)
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
    assert "required: false" not in compose
    assert overlay.count("required: false") == 14
    beat_override = _service_block(overlay, "celery-beat")
    assert "deployment-log-db:" in beat_override
    assert "condition: service_healthy" in beat_override
    assert "required: false" in beat_override
    assert "DB_HOST: ${DB_HOST:-db}" in compose
    assert "DEPLOYMENT_LOG_DB_HOST: ${DEPLOYMENT_LOG_DB_HOST:-deployment-log-db}" in compose
    assert "DEPLOYMENT_LOG_DB_PORT: ${DEPLOYMENT_LOG_DB_PORT:-5432}" in compose


def test_workers_join_matrix_network_only_in_shared_database_mode():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    overlay = (ROOT / "compose.matrix-postgres.yaml").read_text(encoding="utf-8")
    for name in (
        "web",
        "celery",
        "deployment-worker",
        "base-image-worker",
        "celery-beat",
        "log-collector",
        "integration-test",
    ):
        base_block = _service_block(compose, name)
        shared_block = _service_block(overlay, name)
        assert "DB_NAME: ${DB_NAME:-passdb}" in base_block, name
        assert "DB_USER: ${DB_USER:-psguser}" in base_block, name
        assert "DEPLOYMENT_LOG_DB_NAME: ${DEPLOYMENT_LOG_DB_NAME:-deployment_logs}" in base_block, name
        if name == "web":
            assert "- matrix-network" in base_block
        else:
            assert "- matrix-network" not in base_block, name
            assert "- matrix-network" in shared_block, name


def test_shared_postgres_helper_never_removes_volumes_or_changes_synapse_database():
    helper = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")
    docs = (ROOT / "documentation" / "installation.md").read_text(encoding="utf-8")

    assert "docker compose down -v" not in helper
    assert "docker volume rm" not in helper
    assert "paas_deployer_logs" in docs
    assert "Do not" in docs and "synapse" in docs
    assert "docker stop deploy-db deploy-log-db" in docs

def test_shared_postgres_start_preflights_and_repairs_stale_matrix_network():
    helper = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")

    assert "preflight_matrix_postgres_network \"$@\" || exit $?" in helper
    assert 'container_networks "$postgres_container"' in helper
    assert 'docker network inspect "$MATRIX_DOCKER_NETWORK"' in helper
    assert "using detected network" in helper
    assert "correct shared network is not unambiguous" in helper
    assert "export MATRIX_DOCKER_NETWORK" in helper

def test_shared_postgres_resolves_host_alias_separately_from_container_name():
    helper = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "MATRIX_POSTGRES_CONTAINER=$(setting MATRIX_POSTGRES_CONTAINER)" in helper
    assert "resolve_postgres_container()" in helper
    assert "docker ps -q" in helper
    assert ".NetworkSettings.Networks" in helper
    assert "MATRIX_POSTGRES_CONTAINER=" in env_example
    assert "MATRIX_POSTGRES_HOST is a DNS name" in helper
