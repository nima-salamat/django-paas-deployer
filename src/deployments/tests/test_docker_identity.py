from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from deployments.common.docker_identity import (
    candidate_image_refs,
    canonical_image_ref,
    canonical_image_tag,
    canonical_network_name,
    canonical_process_name,
    canonical_remote_image_ref,
    canonical_runtime_process_service_name,
    canonical_service_name,
    canonical_volume_name,
    legacy_service_name_candidates,
    validate_image_repository,
)


SERVICE_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_canonical_service_name_is_the_single_current_contract():
    assert canonical_service_name(
        SERVICE_ID,
        "My-WordPress",
    ) == "app-12345678-my-wordpress"


def test_legacy_service_names_are_lookup_only_and_current_name_is_first():
    assert legacy_service_name_candidates(SERVICE_ID, "WordPress") == (
        "app-12345678-wordpress",
        "12345678-wordpress",
        "local/12345678-wordpress",
    )


def test_network_and_volume_names_preserve_existing_format():
    assert canonical_network_name(SERVICE_ID, "private-net") == "net-12345678-private-net"
    assert canonical_volume_name(SERVICE_ID, "wordpress-data") == "vol-12345678-wordpress-data"


def test_image_repository_supports_namespaces_without_rewriting():
    assert validate_image_repository("paas-base/php-apache") == "paas-base/php-apache"


def test_image_tags_preserve_decimal_deployment_versions():
    assert canonical_image_tag(Decimal("1.00")) == "1.00"
    assert canonical_image_ref("app-12345678-demo", Decimal("1.20")) == "app-12345678-demo:1.20"


def test_remote_swarm_image_ref_supports_registry_port():
    assert canonical_remote_image_ref(
        "app-12345678-demo",
        "1.20",
        registry="registry.example.test:5000",
        namespace="passdeployer",
    ) == "registry.example.test:5000/passdeployer/app-12345678-demo:1.20"


def test_process_container_name_matches_the_previous_orchestrator_shape():
    assert canonical_process_name(
        "app-12345678-demo",
        "worker",
        2,
        "abcdef1234567890",
    ) == "app-12345678-demo-worker-2-1234567890"


def test_process_swarm_service_name_matches_the_previous_revisioning_shape():
    assert canonical_runtime_process_service_name(
        "app-12345678-demo",
        "worker",
    ) == "app-12345678-demo-worker"


def test_candidate_application_image_refs_include_legacy_names_for_discovery():
    assert candidate_image_refs(
        SERVICE_ID,
        "demo",
        "1.00",
    ) == (
        "app-12345678-demo:1.00",
        "12345678-demo:1.00",
        "local/12345678-demo:1.00",
    )


@pytest.mark.parametrize(
    "bad",
    ["", "foo bar", "foo/bar/UPPER", "-bad"],
)
def test_invalid_image_repositories_fail_with_the_central_policy(bad):
    with pytest.raises(Exception):
        validate_image_repository(bad)
