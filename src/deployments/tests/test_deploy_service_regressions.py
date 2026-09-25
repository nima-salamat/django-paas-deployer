from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_service_does_not_reference_undefined_config():
    source = (ROOT / "deployments/celery/services/deploy_service.py").read_text(
        encoding="utf-8"
    )
    assert 'getattr(config, "base_images", {})' not in source

