from deploy.serializers import MaskedDBConfigField


def test_deployment_config_redaction_is_recursive_for_nested_and_dsn_secrets():
    raw = {
        "platform": "postgresql",
        "password": "db-secret",
        "root_password": "root-secret",
        "env": {
            "DATABASE_URL": "postgres://dbuser:db-secret@database.internal/app",
            "APP_SETTINGS": {
                "API_TOKEN": "application-token",
                "DEBUG": "false",
            },
            "PUBLIC_NOTE": "postgres://reader:visible@readonly.internal/report",
        },
        "connection_string": "postgres://user:another-secret@db.internal/app",
    }

    masked = MaskedDBConfigField._redact(raw)

    assert masked["password"] == "[REDACTED]"
    assert masked["root_password"] == "[REDACTED]"
    assert masked["env"]["DATABASE_URL"] == "[REDACTED]"
    assert masked["env"]["APP_SETTINGS"]["API_TOKEN"] == "[REDACTED]"
    assert masked["env"]["APP_SETTINGS"]["DEBUG"] == "false"
    assert masked["connection_string"] == "[REDACTED]"
    assert "reader:[REDACTED]@" in masked["env"]["PUBLIC_NOTE"]


def test_database_credential_permission_never_reveals_nested_application_secrets():
    raw = {
        "platform": "postgresql",
        "username": "app-user",
        "password": "db-secret",
        "root_password": "root-secret",
        "env": {
            "DATABASE_URL": "postgres://dbuser:db-secret@database.internal/app",
            "NESTED": {"API_TOKEN": "application-token"},
        },
    }

    shared_db_view = MaskedDBConfigField._redact(
        raw,
        allow_top_level_db_credentials=True,
    )

    assert shared_db_view["username"] == "app-user"
    assert shared_db_view["password"] == "db-secret"
    assert shared_db_view["root_password"] == "root-secret"
    assert shared_db_view["env"]["DATABASE_URL"] == "[REDACTED]"
    assert shared_db_view["env"]["NESTED"]["API_TOKEN"] == "[REDACTED]"
