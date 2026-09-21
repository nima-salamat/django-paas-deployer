"""Regression coverage for DeployService's explicit config handoff."""

from pathlib import Path


def test_process_deployment_passes_resolved_config_to_orchestrator():
    """The production path must hand the same resolved config to orchestration.

    This is deliberately source-level because the repository's Django/Celery
    runtime dependencies are not available in the lightweight test environment.
    The assertion targets the concrete regression: orchestration must not reach
    into a local variable named _paths_cfg created by another method.
    """
    source = Path("deployments/celery/services/deploy_service.py").read_text()

    assert "_paths_cfg" not in source
    assert 'cfg["resolved_paths"] = dict(paths_cfg)' in source
    assert "def _execute_orchestrator(" in source
    assert "*, cfg: dict," in source
    assert "state_tracker, cfg=cfg," in source
    assert 'cfg.get("resolved_paths", {})' in source


def test_missing_path_configuration_has_a_safe_empty_mapping():
    """Missing paths must resolve to an empty mapping rather than undefined data."""
    source = Path("deployments/celery/services/deploy_service.py").read_text()

    assert 'paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}' in source
    assert 'cfg["resolved_paths"] = dict(paths_cfg)' in source


def test_resolved_paths_are_consumed_from_the_explicit_config_handoff():
    source = Path("deployments/celery/services/deploy_service.py").read_text()
    assert 'cfg.get("resolved_paths", {})' in source
    assert 'document_root=cfg.get("document_root") or cfg.get("resolved_paths", {}).get("document_root")' in source
    assert 'static_dir=cfg.get("static_dir") or cfg.get("resolved_paths", {}).get("static_dir")' in source
    assert 'media_dir=cfg.get("media_dir") or cfg.get("resolved_paths", {}).get("media_dir")' in source


def test_orchestrator_failures_preserve_structured_error_metadata_for_terminal_events():
    source = Path("deployments/core/orchestrator.py").read_text()
    assert '"error_code": exc.code' in source
    assert '"error_category": exc.category' in source
    assert '"technical_message": exc.technical_message' in source
