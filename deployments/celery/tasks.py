# deploy/tasks.py
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.sink import DBAndChannelEventSink
from deployments.core.db_deployer import DBDeployer, DB_PLATFORMS
from deploy.models import Deploy
from services.models import Service
from core.global_settings.config import SERVICE_STATUS_CHOICES

import logging

logger = logging.getLogger(__name__)


def _resolve_platform(deploy) -> str:
    cfg = deploy.config if isinstance(getattr(deploy, "config", None), dict) else {}
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    plan = getattr(getattr(deploy, "service", None), "plan", None)
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    return "docker"


@shared_task(bind=True)
def run_deploy(self, deploy_id):
    """Run an application deployment (zip + Dockerfile). DB platforms redirect to run_db_deploy."""
    try:
        deploy = Deploy.objects.select_related("service", "service__plan").get(pk=deploy_id)
    except Deploy.DoesNotExist:
        return {"error": "deploy_not_found"}

    platform = _resolve_platform(deploy)

    # DB platforms must never enter the zip/Dockerfile pipeline
    if platform in DB_PLATFORMS:
        logger.warning(
            "run_deploy received DB platform '%s' for deploy_id=%s; redirecting to run_db_deploy",
            platform,
            deploy_id,
        )
        return run_db_deploy.apply(args=[str(deploy_id)]).get()

    try:
        with transaction.atomic():
            deploy.status = "pending"
            deploy.started_at = timezone.now()
            deploy.save(update_fields=["status", "started_at"])
    except Exception:
        pass

    sink = DBAndChannelEventSink(deploy_id=deploy.id)

    name = deploy.name
    tag = str(deploy.version) if deploy.version is not None else "latest"
    zip_filename = deploy.zip_file.path if deploy.zip_file else None

    cfg = deploy.config if isinstance(deploy.config, dict) else {}
    dockerfile_text = cfg.get("dockerfile")

    if not dockerfile_text:
        try:
            from core.global_settings import config as global_config
            dockerfile_text = getattr(global_config.Config, platform, None)
        except Exception:
            dockerfile_text = None

    if not zip_filename:
        try:
            deploy.status = "failed"
            deploy.error_message = "Missing zip file for deployment."
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "error_message", "completed_at"])
            Service.objects.filter(pk=deploy.service_id).update(
                status=SERVICE_STATUS_CHOICES.FAILED,
                deploy_started=None,
                task_id=None,
            )
        except Exception:
            pass
        return {"error": "Missing zip file for deployment."}

    if not dockerfile_text:
        dockerfile_text = 'FROM alpine:3.18\nCMD ["/bin/sh"]'

    networks = cfg.get("networks", []) if isinstance(cfg, dict) else []
    volumes = cfg.get("volumes", []) if isinstance(cfg, dict) else []
    max_cpu = cfg.get("max_cpu")
    max_ram = cfg.get("max_ram")
    port = cfg.get("port")
    read_only = cfg.get("read_only", True)
    platform_type = cfg.get("platform_type") or "APP"

    raw_env = cfg.get("env") or {}
    environment = {str(k): str(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else {}
    server_type = cfg.get("server_type") or None
    entry_point = cfg.get("entry_point") or None
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
        orchestrator_deploy.deploy()
        deploy.refresh_from_db()
        if deploy.status != "succeeded":
            deploy.status = "succeeded"
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "completed_at"])
        Service.objects.filter(pk=deploy.service_id).update(
            status=SERVICE_STATUS_CHOICES.RUNNING,
            deployed_at=timezone.now(),
            deploy_started=None,
            task_id=None,
        )
        return {"result": "ok"}
    except Exception as exc:
        try:
            deploy.refresh_from_db()
            deploy.status = "failed"
            deploy.error_message = str(exc)
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["status", "error_message", "completed_at"])
            Service.objects.filter(pk=deploy.service_id).update(
                status=SERVICE_STATUS_CHOICES.FAILED,
                deploy_started=None,
                task_id=None,
            )
        except Exception:
            pass
        return {"error": str(exc)}


@shared_task(bind=True)
def cancel_deploy(self, deploy_id):
    """Mark a deploy as cancel_requested."""
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
    Deploy a database container from Deploy.config credentials.

    No zip file. No Dockerfile.
    Platform: config["platform"] → service.plan.platform → mysql.
    """
    try:
        deploy = Deploy.objects.select_related(
            "service", "service__plan", "service__network"
        ).get(pk=deploy_id)
    except Deploy.DoesNotExist:
        return {"error": "deploy_not_found"}

    service = deploy.service
    cfg = dict(deploy.config) if isinstance(deploy.config, dict) else {}

    platform = str(cfg.get("platform") or "").strip().lower()
    if not platform and service.plan_id and getattr(service, "plan", None):
        platform = str(getattr(service.plan, "platform", "") or "").strip().lower()
    if not platform:
        platform = "mysql"

    # If somehow called for an app platform, hand off
    if platform not in DB_PLATFORMS:
        logger.warning(
            "run_db_deploy received non-DB platform '%s' for deploy_id=%s; redirecting to run_deploy",
            platform,
            deploy_id,
        )
        return run_deploy.apply(args=[str(deploy_id)]).get()

    # Persist platform so later start/rebuild keep routing correctly
    if cfg.get("platform") != platform:
        cfg["platform"] = platform
        Deploy.objects.filter(pk=deploy.pk).update(config=cfg)

    # Inject plan resource limits
    plan = service.plan
    if plan:
        if cfg.get("max_cpu") is None and getattr(plan, "max_cpu", None) is not None:
            cfg["max_cpu"] = plan.max_cpu
        if cfg.get("max_ram") is None and getattr(plan, "max_ram", None) is not None:
            cfg["max_ram"] = plan.max_ram

    # Private network
    if service.network_id and getattr(service, "network", None):
        nets = list(cfg.get("networks") or [])
        net_name = service.network.name
        if net_name and net_name not in nets:
            nets.append(net_name)
        cfg["networks"] = nets

    try:
        with transaction.atomic():
            deploy.status = "running"
            deploy.started_at = timezone.now()
            deploy.stage = "db_deploy"
            deploy.progress = 5
            deploy.status_message = f"Deploying database ({platform})..."
            deploy.error_message = ""
            deploy.save(
                update_fields=[
                    "status",
                    "started_at",
                    "stage",
                    "progress",
                    "status_message",
                    "error_message",
                ]
            )
            Service.objects.filter(pk=service.pk).update(
                status=SERVICE_STATUS_CHOICES.DEPLOYING,
                deploy_started=timezone.now(),
            )
    except Exception:
        logger.exception("run_db_deploy failed to mark running for %s", deploy_id)

    sink = DBAndChannelEventSink(deploy_id=deploy.id)
    container_name = service.get_docker_service_name()

    result = DBDeployer().deploy(
        container_name=container_name,
        platform=platform,
        cfg=cfg,
        event_sink=sink,
        deployment_id=str(deploy.id),
    )

    now = timezone.now()
    if result.success:
        try:
            deploy.refresh_from_db()
            deploy.status = "succeeded"
            deploy.completed_at = now
            deploy.progress = 100
            deploy.stage = "finished"
            deploy.status_message = result.message
            deploy.error_message = ""
            deploy.container_status = "running"
            deploy.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "progress",
                    "stage",
                    "status_message",
                    "error_message",
                    "container_status",
                ]
            )
            Service.objects.filter(pk=service.pk).update(
                status=SERVICE_STATUS_CHOICES.RUNNING,
                deployed_at=now,
                deploy_started=None,
                task_id=None,
            )
        except Exception:
            logger.exception("run_db_deploy failed to persist success for %s", deploy_id)
        return {"result": "ok", "port": result.port}

    try:
        deploy.refresh_from_db()
        deploy.status = "failed"
        deploy.error_message = result.error or result.message
        deploy.completed_at = now
        deploy.stage = "db_deploy"
        deploy.save(update_fields=["status", "error_message", "completed_at", "stage"])
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )
    except Exception:
        logger.exception("run_db_deploy failed to persist failure for %s", deploy_id)
    return {"error": result.message}


def handle_deploy_start(deploy_id):
    """Legacy wrapper — enqueue run_deploy (which redirects DB → run_db_deploy)."""
    try:
        if hasattr(deploy_id, "id"):
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
    """Legacy wrapper — enqueue cancel_deploy."""
    try:
        if hasattr(deploy_id, "id"):
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
