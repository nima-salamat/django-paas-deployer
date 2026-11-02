from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_database_config_mutations_create_immutable_revisions():
    source = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    update_config = source.split("def update_db_config", 1)[1].split(
        "def update(", 1
    )[0]

    assert "materialize_revision_config(locked.revision)" in update_config
    assert "ensure_revision_for_deploy(" in update_config
    assert "force_new=True" in update_config
    assert "revision_id" in update_config


def test_database_credential_rotation_is_rejected_when_engine_cannot_reconcile_it():
    source = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    update_config = source.split("def update_db_config", 1)[1].split(
        "def update(", 1
    )[0]

    assert '"postgresql", "mongodb", "mongo", "oracle"' in update_config
    assert "DATABASE_CREDENTIAL_ROTATION_UNSUPPORTED" in update_config
    assert "existing database was not changed" in update_config
    assert 'platform == "redis"' in update_config
    assert "sensitive_env_tokens" in update_config


def test_generic_deploy_update_cannot_bypass_database_revision_creation():
    source = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    generic_update = source.split("def update(self, request, pk=None", 1)[1].split(
        "def destroy(", 1
    )[0]

    assert "database_config_revision_required" in generic_update
    assert "update_db_config" in generic_update
