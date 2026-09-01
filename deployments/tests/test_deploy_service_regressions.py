

def test_deploy_service_does_not_reference_undefined_config():
    from pathlib import Path
    source = Path("deployments/celery/services/deploy_service.py").read_text()
    assert 'getattr(config, "base_images", {})' not in source

