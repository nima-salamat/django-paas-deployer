from celery import shared_task, current_task
from django.utils import timezone
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.sink import DBAndChannelEventSink
from deployments.core.db_deployer import DBDeployer, DB_PLATFORMS
from deploy.models import Deploy
from django.db import transaction


@shared_task(bind=True)
def run_deploy(self, deploy_id):
    """Run a deployment using DeploymentOrchestrator via the Deploy facade.

    The task updates Deploy status/progress through the event sink which writes
    DeployLog entries and sends websocket messages.
    """
    # Load deploy
    try:
        deploy = Deploy.objects.select_related("service").get(pk=deploy_id)
    except Deploy.DoesNotExist:
        return {"error": "deploy_not_found"}

    # Set task id on related service (optional)
    try:
        with transaction.atomic():
            deploy.status = "pending"
            deploy.started_at = timezone.now()
            deploy.save(update_fields=["status", "started_at"])
    except Exception:
        pass

    sink = DBAndChannelEventSink(deploy_id=deploy.id)

    # Prepare parameters for Deploy facade
    name = deploy.name
    tag = str(deploy.version) if deploy.version is not None else "latest"
    zip_filename = deploy.zip_file.path if deploy.zip_file else None
    # Determine dockerfile template: prefer deploy.config['dockerfile'] then global templates
    dockerfile_text = None
    try:
        cfg = deploy.config if isinstance(deploy.config, dict) else {}
        platform = _resolve_platform(deploy)
        is_db = platform in DB_PLATFORMS
        if is_db and not cfg.get("platform"):
                cfg = {**cfg, "platform": platform}
                Deploy.objects.filter(pk=deploy.pk).update(config=cfg)
    except Exception:
        platform = "docker"

    # DB platforms must use run_db_deploy — redirect automatically if somehow
    # called via the wrong task to avoid confusing failures.
    if platform in DB_PLATFORMS:
        return run_db_deploy.apply(args=[deploy_id]).get()
    
    # If no dockerfile_text, try to pull from global templates
    if not dockerfile_text:
        try:
            from core.global_settings import config as global_config
            dockerfile_text = getattr(global_config.Config, platform)
        except Exception:
            dockerfile_text = "FROM alpine:3.18\nCMD [\"/bin/sh\"]"

    # Pass networks / volumes and resource limits from deploy.config
    networks = cfg.get("networks", []) if isinstance(cfg, dict) else []
    volumes = cfg.get("volumes", []) if isinstance(cfg, dict) else []
    max_cpu = cfg.get("max_cpu")
    max_ram = cfg.get("max_ram")
    port = cfg.get("port")
    read_only = cfg.get("read_only", True)
    platform_type = cfg.get("platform_type") or "APP"

    # --- New deploy config parameters ---
    # env: dict of runtime environment variables, e.g. {"DEBUG": "0", "SECRET_KEY": "..."}
    # Values must be strings; non-string values are coerced.
    raw_env = cfg.get("env") or {}
    environment = {str(k): str(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else {}

    # server_type: "asgi" | "wsgi" | None  — overrides auto-detection for Django
    server_type = cfg.get("server_type") or None

    # entry_point: custom CMD string, e.g. "python manage.py runserver 0.0.0.0:8000"
    entry_point = cfg.get("entry_point") or None

    # celery: bool — add a Celery worker process via supervisord
    # celery_beat: bool — also add Celery beat (only meaningful when celery=True)
    celery = bool(cfg.get("celery", False))
    celery_beat = bool(cfg.get("celery_beat", False))

    orchestrator_deploy = OrchestratorDeploy(
        name=name,
        tag=tag,
        zip_filename=zip_filename,
        dockerfile_text=dockerfile_text,
        max_cpu=max_cpu,
        max_ram=max_ram,
        networks=networks,
        volumes=volumes,
        port=port,
        read_only=read_only,
        platform=platform,
        platform_type=platform_type,
        event_sink=sink,
        deployment_id=str(deploy.id),
        environment=environment,
        server_type=server_type,
        entry_point=entry_point,
        celery=celery,
        celery_beat=celery_beat,
    )

    try:
        # Run deployment synchronously inside task
        orchestrator_deploy.deploy()
        # update Deploy final status if not set by sink
        deploy.refresh_from_db()
        if deploy.status != "succeeded":
            deploy.status = "succeeded"
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "completed_at"])
        return {"result": "ok"}
    except Exception as exc:
        # Sink should have recorded error; ensure deploy is marked failed
        try:
            deploy.refresh_from_db()
            deploy.status = "failed"
            deploy.error_message = str(exc)
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        return {"error": str(exc)}


@shared_task(bind=True)
def cancel_deploy(self, deploy_id):
    """Mark a deploy as cancel_requested. The running task checks this flag and will abort soon."""
    try:
        deploy = Deploy.objects.get(pk=deploy_id)
        deploy.cancel_requested = True
        deploy.save(update_fields=["cancel_requested"])
        return {"result": "cancel_requested"}
    except Deploy.DoesNotExist:
        return {"error": "not_found"}


@shared_task(bind=True)
def run_db_deploy(self, deploy_id):
    """
    Deploy a database container (MySQL, PostgreSQL, MariaDB, MongoDB, Redis,
    Oracle) from credentials stored in Deploy.config.

    No zip file is required.  The platform is read from cfg["platform"].
    Credentials are injected at container runtime — never baked into an image.

    This task is also triggered by rebuild actions to recreate the container
    with updated credentials after an update_db_config call.
    """
    try:
        deploy = Deploy.objects.select_related("service").get(pk=deploy_id)
    except Deploy.DoesNotExist:
        return {"error": "deploy_not_found"}

    # Mark as running
    try:
        with transaction.atomic():
            deploy.status = "pending"
            deploy.started_at = timezone.now()
            deploy.save(update_fields=["status", "started_at"])
    except Exception:
        pass

    sink = DBAndChannelEventSink(deploy_id=deploy.id)
    cfg = deploy.config or {}
    platform = cfg.get("platform") or "mysql"
    container_name = deploy.service.get_docker_service_name()

    result = DBDeployer().deploy(
        container_name=container_name,
        platform=platform,
        cfg=cfg,
        event_sink=sink,
        deployment_id=str(deploy.id),
    )

    if result.success:
        try:
            deploy.refresh_from_db()
            if deploy.status != "succeeded":
                deploy.status = "succeeded"
                deploy.completed_at = timezone.now()
                deploy.save(update_fields=["status", "completed_at"])
        except Exception:
            pass
        return {"result": "ok", "port": result.port}
    else:
        try:
            deploy.refresh_from_db()
            deploy.status = "failed"
            deploy.error_message = result.error or result.message
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        return {"error": result.message}


# Backwards-compatible wrappers for older imports that expected
# `handle_deploy_start` and `handle_deploy_stop`. These delegate to
# the new Celery tasks so external callers that import the old symbols
# continue to work.

def handle_deploy_start(deploy_id):
    """Legacy synchronous wrapper that enqueues the new run_deploy task."""
    try:
        # If someone passed a model instance, accept it
        if hasattr(deploy_id, 'id'):
            deploy_id = str(deploy_id.id)
        else:
            deploy_id = str(deploy_id)
    except Exception:
        deploy_id = str(deploy_id)
    try:
        run_deploy.delay(deploy_id)
        return {"result": "enqueued"}
    except Exception as exc:
        return {"error": str(exc)}


def handle_deploy_stop(deploy_id):
    """Legacy wrapper that enqueues cancel_deploy task."""
    try:
        if hasattr(deploy_id, 'id'):
            deploy_id = str(deploy_id.id)
        else:
            deploy_id = str(deploy_id)
    except Exception:
        deploy_id = str(deploy_id)
    try:
        cancel_deploy.delay(deploy_id)
        return {"result": "cancel_enqueued"}
    except Exception as exc:
        return {"error": str(exc)}
