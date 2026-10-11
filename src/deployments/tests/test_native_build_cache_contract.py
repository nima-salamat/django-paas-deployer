from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_native_swarm_build_registers_image_for_retention_and_service_cleanup():
    source = (
        ROOT / "src" / "deployments" / "celery" / "services" / "deploy_service.py"
    ).read_text(encoding="utf-8")
    build_start = source.index("def build_plan(current_context):")
    build_end = source.index("strategy = CallbackDeploymentStrategy", build_start)
    build_plan = source[build_start:build_end]

    built = build_plan.index("built_image = image.create(")
    accounted = build_plan.index("record_application_image(str(deploy_item.pk), built_image)")
    continue_check = build_plan.index("current_context.assert_can_continue()", built)

    assert built < accounted < continue_check
    assert "enforce_service_cache_quota(str(cache_artifact.service_id))" in build_plan
    assert "enforce_user_cache_quota(str(cache_artifact.user_id))" in build_plan
