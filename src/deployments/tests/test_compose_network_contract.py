from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def _network_names(service):
    networks = service.get("networks") or ()
    return set(networks if isinstance(networks, list) else networks.keys())


def test_proxy_network_is_external_and_only_traefik_joins_the_control_plane_stack():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))

    assert compose["networks"]["proxy_net"] == {
        "name": "proxy_net",
        "external": True,
    }
    attached_services = {
        name
        for name, service in compose["services"].items()
        if "proxy_net" in _network_names(service)
    }
    assert attached_services == {"traefik"}


def test_compose_wrapper_prepares_proxy_network_for_the_selected_runtime():
    script = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")

    assert 'prepare_proxy_network "$@" || exit $?' in script
    assert "SWARM_ENABLED is enabled but this Docker node is not an active Swarm node" in script
    assert "expected_driver=overlay" in script
    assert "expected_scope=swarm" in script
    assert "docker network create --driver overlay --attachable proxy_net" in script
    assert "expected_driver=bridge" in script
    assert "expected_scope=local" in script
    assert "docker network create --driver bridge proxy_net" in script
    assert "actual_scope" in script
    assert "docker network inspect --format '{{.Attachable}}' proxy_net" in script


def test_runtime_log_network_driver_matches_selected_runtime():
    script = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")
    selection = script.split("prepare_runtime_log_ingestion() {", 1)[1].split(
        "# Read-only/lifecycle commands", 1
    )[0]

    assert "runtime_mode=swarm" in selection
    assert "expected_driver=overlay" in selection
    assert "runtime_mode=docker" in selection
    assert "expected_driver=bridge" in selection


def test_dotenv_reader_strips_quotes_before_exporting_secret_values():
    script = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")

    assert "substr(value, 1, 1)" in script
    assert "substr(value, length(value), 1)" in script
