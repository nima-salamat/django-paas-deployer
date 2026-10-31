from deployments.management.commands.migrate_runtime_log_driver import updated_service_spec


def test_updated_service_spec_preserves_existing_runtime_configuration():
    original = {
        "Name": "app-example",
        "Labels": {"managed-by": "django-paas-deployer"},
        "Mode": {"Replicated": {"Replicas": 2}},
        "UpdateConfig": {"Parallelism": 1},
        "TaskTemplate": {
            "ForceUpdate": 4,
            "ContainerSpec": {
                "Image": "example:latest",
                "Command": ["python", "app.py"],
                "Labels": {"passdeployer.service": "service-1"},
            },
            "Placement": {"Constraints": ["node.role == manager"]},
        },
    }

    migrated = updated_service_spec(original, {"fluentd-address": "unix:///run/log.sock"})

    assert migrated["TaskTemplate"]["LogDriver"] == {
        "Name": "fluentd",
        "Options": {"fluentd-address": "unix:///run/log.sock"},
    }
    assert migrated["TaskTemplate"]["ForceUpdate"] == 5
    assert migrated["TaskTemplate"]["ContainerSpec"] == original["TaskTemplate"]["ContainerSpec"]
    assert migrated["TaskTemplate"]["Placement"] == original["TaskTemplate"]["Placement"]
    assert migrated["Mode"] == original["Mode"]
    assert migrated["UpdateConfig"] == original["UpdateConfig"]
    assert original["TaskTemplate"].get("LogDriver") is None


def test_updated_service_spec_recovers_from_invalid_force_update_value():
    migrated = updated_service_spec(
        {"TaskTemplate": {"ForceUpdate": "unknown"}},
        {"mode": "non-blocking"},
    )
    assert migrated["TaskTemplate"]["ForceUpdate"] == 1
