from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]


def _source(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def _tree(*parts: str) -> ast.Module:
    return ast.parse(_source(*parts))


def test_swarm_adapter_has_native_plan_boundary_without_legacy_config():
    source = _source("runtime", "swarm", "adapter.py")
    assert "DeploymentConfig" not in source
    assert "DeploymentPlanCompatibilityCompiler" not in source
    assert "deployment_config" not in source
    assert "def _plan_config(plan" in source


def test_native_deploy_service_uses_lifecycle_executor_for_swarm():
    source = _source("celery", "services", "deploy_service.py")
    assert "DeploymentLifecycleExecutor(store).execute(" in source
    assert "CallbackDeploymentStrategy(build_plan=build_plan)" in source
    assert "if swarm_enabled() and execution_plan is not None:" in source
    # The old facade is retained only as a non-Swarm compatibility path.
    branch = source.index("if swarm_enabled() and execution_plan is not None:")
    legacy = source.index("deployer = DeployFacade(")
    assert branch < legacy


def test_native_plan_carries_artifact_and_release_identity():
    source = _source("planning", "plan.py")
    assert "artifact_digest: str" in source
    assert "release_id: str | None" in source
    assert "release_spec:" in source


def test_runtime_apply_and_rollback_are_cancellable():
    contract = _source("runtime", "contract.py")
    assert "def apply(self, plan: Any, *, operation_key: str, cancel_check:" in contract
    assert "cancel_check: Callable[[], bool] | None = None" in contract
    assert "def rollback(" in contract
    assert "cancel_check: Callable[[], bool] | None = None" in contract


def test_swarm_capability_matches_supported_replica_range():
    source = _source("runtime", "swarm", "adapter.py")
    assert '"replica_limit": "0..8"' in source
    swarm = _source("core", "swarm.py")
    assert "1 <= replicas <= 8" in swarm or "0 <= replicas <= 8" in swarm


def test_release_and_artifact_are_separate_from_cache_artifacts():
    models = _source("..", "deploy", "models.py")
    assert "class BuildArtifact(" in models
    assert "class Release(" in models
    assert "class BuildCacheArtifact(" in models
    assert 'release_reference = models.ForeignKey(' in models
    assert 'artifact = models.ForeignKey(' in models


def test_release_fingerprint_is_content_deterministic():
    models = ast.parse(_source("..", "deploy", "models.py"))
    release = next(node for node in models.body if isinstance(node, ast.ClassDef) and node.name == "Release")
    fingerprint = next(
        node for node in release.body
        if isinstance(node, ast.FunctionDef) and node.name == "fingerprint"
    )
    assert any(isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "sha256" for node in ast.walk(fingerprint))


def test_new_migration_is_db_only_and_follows_current_deploy_head():
    migration = _source("..", "deploy", "migrations", "0032_release_and_build_artifact.py")
    assert '("deploy", "0027_deploylog_event_id")' in migration
    forbidden = ("Docker", "Celery", "Redis", "requests.", "urllib.")
    assert not any(token in migration for token in forbidden)


def test_runtime_spec_redacts_sensitive_environment_from_native_plan():
    source = _source("planning", "runtime_spec.py")
    assert "def from_plan(" in source
    assert "_is_sensitive_key(key)" in source
    assert '"[SECRET_REF]"' in source
