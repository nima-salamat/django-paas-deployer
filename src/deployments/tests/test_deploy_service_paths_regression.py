"""Regression coverage for DeployService's explicit config handoff."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(path):
    """Read repository source independently of pytest's working directory."""
    return (ROOT / path).read_text(encoding="utf-8")


def test_process_deployment_passes_resolved_config_to_orchestrator():
    """The production path must hand the same resolved config to orchestration.

    This is deliberately source-level because the repository's Django/Celery
    runtime dependencies are not available in the lightweight test environment.
    The assertion targets the concrete regression: orchestration must not reach
    into a local variable named _paths_cfg created by another method.
    """
    source = _source("deployments/celery/services/deploy_service.py")

    assert "_paths_cfg" not in source
    assert 'cfg["resolved_paths"] = dict(paths_cfg)' in source
    assert "def _execute_orchestrator(" in source
    assert "*, cfg: dict," in source
    assert "state_tracker,\n                cfg=cfg," in source
    assert 'cfg.get("resolved_paths", {})' in source


def test_missing_path_configuration_has_a_safe_empty_mapping():
    """Missing paths must resolve to an empty mapping rather than undefined data."""
    source = _source("deployments/celery/services/deploy_service.py")

    assert 'paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}' in source
    assert 'cfg["resolved_paths"] = dict(paths_cfg)' in source


def test_resolved_paths_are_consumed_from_the_explicit_config_handoff():
    source = _source("deployments/celery/services/deploy_service.py")
    assert 'cfg.get("resolved_paths", {})' in source
    assert 'document_root=cfg.get("document_root") or cfg.get("resolved_paths", {}).get("document_root")' in source
    assert 'static_dir=cfg.get("static_dir") or cfg.get("resolved_paths", {}).get("static_dir")' in source
    assert 'media_dir=cfg.get("media_dir") or cfg.get("resolved_paths", {}).get("media_dir")' in source


def test_orchestrator_failures_preserve_structured_error_metadata_for_terminal_events():
    source = _source("deployments/core/orchestrator.py")
    assert '"error_code": exc.code' in source
    assert '"error_category": exc.category' in source
    assert '"technical_message": exc.technical_message' in source

def test_activation_callback_is_forwarded_through_the_service_orchestrator_boundary():
    source = _source("deployments/celery/services/deploy_service.py")
    assert "*, cfg: dict, activation_callback=None," in source
    assert "cfg=cfg, activation_callback=activation_callback," in source
    assert "activation_callback=activation_callback," in source

def test_revision_snapshot_is_local_and_catalog_warning_uses_service_from_deploy_item():
    """Catalog build normalization must not reference undefined legacy locals."""
    source = _source("deployments/celery/services/deploy_service.py")

    assert "revision_config" not in source
    assert 'revision_snapshot = (' in source
    assert 'materialize_revision_config(deploy_item.revision)' in source
    assert 'using immutable revision Dockerfile for build. deployment=%s service=%s' in source
    assert '                    deploy_item.pk,\n                    deploy_item.service.pk,\n' in source

def test_execute_orchestrator_does_not_reference_process_local_revision_snapshot():
    """The orchestration boundary must consume cfg, not _process_deployment locals."""
    source = _source("deployments/celery/services/deploy_service.py")
    start = source.index("    def _execute_orchestrator(")
    end = source.index("    def _execute_native_swarm_lifecycle(", start)
    method_source = source[start:end]

    assert "revision_snapshot" not in method_source
    assert 'cfg.get("source_kind")' in method_source
