

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
    process_start = source.index("    def _process_deployment(")
    process_end = source.index("    def _execute_orchestrator(", process_start)
    process_source = source[process_start:process_end]
    assert 'getattr(service, "source_kind", "")' not in process_source
    assert 'getattr(deploy_item.service, "source_kind", "")' in process_source

def test_execute_orchestrator_does_not_reference_process_local_revision_snapshot():
    """The orchestration boundary must consume cfg, not _process_deployment locals."""
    source = _source("deployments/celery/services/deploy_service.py")
    start = source.index("    def _execute_orchestrator(")
    end = source.index("    def _execute_native_swarm_lifecycle(", start)
    method_source = source[start:end]

    assert "revision_snapshot" not in method_source
    assert 'cfg.get("source_kind")' in method_source