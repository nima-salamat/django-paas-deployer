"""
Long-running Docker event reconciler for deployments.

Docker is the source of truth for runtime lifecycle.  Celery executes the
operation; this process listens to the daemon and immediately reflects
container start/die/oom/health/destroy events into Deploy + DeployLog and the
existing Channels WebSocket pipeline.

The process is deliberately independent from Celery/Beat so a busy queue or
stuck worker cannot delay runtime-state updates.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import docker
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from deploy.models import Deploy, DeploymentStatusChoices
from deployments.core.manager.client_manager import get_docker_client

logger = logging.getLogger(__name__)

MANAGED_LABEL = "managed-by=django-paas-deployer"
ACTIVE = {
    DeploymentStatusChoices.PENDING,
    DeploymentStatusChoices.RUNNING,
    DeploymentStatusChoices.ROLLING_BACK,
}


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("Action") or event.get("status") or "").strip().lower()


def _deployment_id(event: dict[str, Any]) -> str | None:
    attrs = ((event.get("Actor") or {}).get("Attributes") or {})
    value = attrs.get("deployment.id")
    return str(value) if value else None


def _attrs(event: dict[str, Any]) -> dict[str, Any]:
    return ((event.get("Actor") or {}).get("Attributes") or {})


class Command(BaseCommand):
    help = "Consume Docker Engine events and reconcile deployment runtime state."

    def handle(self, *args, **options):
        backoff = 1.0
        max_backoff = 30.0
        while True:
            try:
                self._consume_forever()
                backoff = 1.0
            except KeyboardInterrupt:
                self.stdout.write("Docker event consumer stopped.")
                return
            except Exception:
                logger.exception("Docker event consumer disconnected; reconnecting in %.1fs", backoff)
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 2)

    def _consume_forever(self):
        client = get_docker_client()
        filters = {"type": "container", "label": [MANAGED_LABEL]}
        logger.info("Docker event consumer connected with filters=%s", filters)
        for event in client.events(decode=True, filters=filters):
            if not isinstance(event, dict):
                continue
            try:
                self._handle_event(event)
            except Exception:
                logger.exception("Failed to process Docker event: %r", event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        action = _event_type(event)
        if action not in {
            "create", "start", "health_status", "die", "oom", "kill",
            "stop", "destroy", "restart", "rename",
        }:
            return

        deploy_id = _deployment_id(event)
        if not deploy_id:
            return

        try:
            deploy = Deploy.objects.select_related("service").get(pk=deploy_id)
        except (Deploy.DoesNotExist, ValueError):
            logger.warning("Docker event references unknown deployment.id=%s", deploy_id)
            return

        attrs = _attrs(event)
        container_id = ((event.get("Actor") or {}).get("ID") or "")[:12]
        status = str(event.get("status") or action)
        exit_code = attrs.get("exitCode") or attrs.get("exit_code")
        health_status = attrs.get("health_status")
        now = timezone.now()

        # Event persistence is best-effort through the same pipeline used by
        # the worker, so WebSocket subscribers see Docker-generated events too.
        def log_event(stage: str, message: str, level: str = "info", progress=None, details=None):
            try:
                from deploy.event_pipeline import DeploymentEventPipeline
                from deployments.core.types import DeploymentEvent
                DeploymentEventPipeline(deploy).record(
                    DeploymentEvent(
                        stage=stage,
                        message=message,
                        level=level,
                        progress=progress,
                        details=details or {},
                    )
                )
            except Exception:
                logger.exception("Failed to persist Docker event for deploy %s", deploy.pk)

        with transaction.atomic():
            locked = Deploy.objects.select_for_update().select_related("service").get(pk=deploy.pk)
            service = locked.service

            if action == "create":
                if locked.status in ACTIVE:
                    Deploy.objects.filter(pk=locked.pk).update(
                        container_status="created",
                        status_message="Deployment container created.",
                    )
                log_event("docker_container_create", f"Docker created deployment container {container_id}.", details={"container_id": container_id})
                return

            if action == "start":
                if locked.status in ACTIVE:
                    Deploy.objects.filter(pk=locked.pk).update(
                        container_status="running",
                        stage="container_running",
                        progress=max(int(locked.progress or 0), 86),
                        status_message="Deployment container is running.",
                    )
                log_event("container_running", f"Docker started deployment container {container_id}.", progress=86, details={"container_id": container_id})
                return

            if action == "health_status":
                hs = str(health_status or status).lower()
                if "healthy" in hs and locked.status in ACTIVE:
                    Deploy.objects.filter(pk=locked.pk).update(
                        health_status="healthy",
                        status_message="Deployment health check passed.",
                    )
                    log_event("health_check", "Docker healthcheck reported healthy.", progress=max(int(locked.progress or 0), 92), details={"container_id": container_id, "health_status": hs})
                    return
                if "unhealthy" in hs and locked.status in ACTIVE:
                    Deploy.objects.filter(pk=locked.pk).update(
                        status=DeploymentStatusChoices.FAILED,
                        stage="health_check",
                        progress=100,
                        status_message="Docker healthcheck reported unhealthy.",
                        error_message="Docker healthcheck reported unhealthy.",
                        completed_at=now,
                        health_status="unhealthy",
                        container_status="unhealthy",
                    )
                    log_event("health_check", "Docker healthcheck reported unhealthy.", level="error", progress=100, details={"container_id": container_id, "health_status": hs})
                    return

            if action == "oom":
                if locked.status in ACTIVE or locked.status == DeploymentStatusChoices.SUCCEEDED:
                    Deploy.objects.filter(pk=locked.pk).update(
                        status=DeploymentStatusChoices.FAILED,
                        stage="container_oom",
                        progress=100,
                        status_message="Deployment container was killed by the kernel due to OOM.",
                        error_message="Container out-of-memory (OOM). Reduce worker count or memory usage, or increase the service plan.",
                        completed_at=now,
                        container_status="oom",
                    )
                    try:
                        from deployments.core.state.manager import StateManager
                        StateManager.mark_service_failed(service.pk)
                    except Exception:
                        logger.exception("Failed to mark service failed after OOM: service=%s", service.pk)
                    log_event("container_oom", "Docker reported an out-of-memory kill.", level="error", progress=100, details={"container_id": container_id})
                return

            if action in {"die", "kill", "stop", "destroy"}:
                # A user-initiated stop is represented by service STOPPING.
                if getattr(service, "status", None) == "stopping":
                    if action in {"stop", "die", "destroy"}:
                        try:
                            from deployments.core.state.manager import StateManager
                            StateManager.mark_service_stopped(service.pk)
                        except Exception:
                            pass
                    log_event("container_stopped", f"Deployment container stopped ({action}).", level="warning", progress=100, details={"container_id": container_id, "action": action})
                    return

                if locked.cancel_requested or locked.status == DeploymentStatusChoices.CANCELLED:
                    Deploy.objects.filter(pk=locked.pk).update(
                        status=DeploymentStatusChoices.CANCELLED,
                        stage="cancelled",
                        progress=100,
                        status_message="Deployment container stopped after cancellation.",
                        completed_at=now,
                        container_status="stopped",
                    )
                    try:
                        from deployments.core.state.manager import StateManager
                        StateManager.mark_service_stopped(service.pk)
                    except Exception:
                        logger.exception("Failed to mark service stopped after cancellation: service=%s", service.pk)
                    log_event("cancelled", "Docker confirmed the cancelled deployment container stopped.", level="warning", progress=100, details={"container_id": container_id, "action": action, "exit_code": exit_code})
                    return

                if locked.status in ACTIVE or locked.status == DeploymentStatusChoices.SUCCEEDED:
                    detail = f"Deployment container exited (action={action}, exit_code={exit_code})."
                    Deploy.objects.filter(pk=locked.pk).update(
                        status=DeploymentStatusChoices.FAILED,
                        stage="container_exit",
                        progress=100,
                        status_message=detail,
                        error_message=detail,
                        completed_at=now,
                        container_status="stopped",
                    )
                    try:
                        from deployments.core.state.manager import StateManager
                        StateManager.mark_service_failed(service.pk)
                    except Exception:
                        logger.exception("Failed to mark service failed after container exit: service=%s", service.pk)
                    log_event("container_exit", detail, level="error", progress=100, details={"container_id": container_id, "action": action, "exit_code": exit_code})
                return

            if action == "restart" and locked.status in ACTIVE:
                Deploy.objects.filter(pk=locked.pk).update(
                    container_status="restarting",
                    status_message="Docker restarted the deployment container.",
                )
                log_event("container_restart", "Docker restarted deployment container.", level="warning", details={"container_id": container_id})
                return

            if action == "rename":
                log_event("container_rename", "Docker renamed deployment container during replacement.", details={"container_id": container_id, "name": attrs.get("name")})
