from pathlib import Path

from deployments.common.docker_identity import validate_image_repository


def _source():
    root = Path(__file__).resolve().parents[2]
    return (root / "deployments" / "core" / "manager" / "image_manager.py").read_text()


def test_image_manager_delegates_repository_validation_to_central_identity_policy():
    text = _source()
    assert "validate_image_repository" in text
    assert "def _validate_image_name" in text
    assert "return validate_image_repository(name)" in text


def test_repository_validation_supports_namespaced_repositories():
    assert validate_image_repository("paas-base/php-apache") == "paas-base/php-apache"
    assert validate_image_repository("registry.example.test/app/runtime") == "registry.example.test/app/runtime"


def test_repository_validation_rejects_non_lowercase_or_invalid_components():
    import pytest
    with pytest.raises(Exception):
        validate_image_repository("PHP/appliCation")
    with pytest.raises(Exception):
        validate_image_repository("bad//repository")
