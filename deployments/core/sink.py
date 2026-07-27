from typing import Callable, Any
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from deploy.models import Deploy, DeployLog


class DBAndChannelEventSink:
    """Sink callable that persists DeploymentEvent to DB (DeployLog) and
    notifies websocket clients via Channels group messages.

    Usage: sink = DBAndChannelEventSink(deployment_id)
           logger = DeploymentLogger(deployment_id=deployment_id, sink=sink)
    """

    def __init__(self, deployment_id):
        self.deployment_id = str(deployment_id)
        self.channel_layer = get_channel_layer()
        # group name where websocket consumers listen
        self.group_name = f"deploy_{self.deployment_id}"

    def __call__(self, event) -> None:
        # event: deployments.core.types.DeploymentEvent
        # Persist to DB
        try:
            deploy = Deploy.objects.filter(pk=self.deployment_id).first()
            # Create DeployLog
            DeployLog.objects.create(
                deploy=deploy,
                service=deploy.service if deploy else None,
                stage=event.stage,
                level=event.level,
                message=event.message,
                progress=event.progress,
                details=event.details or {},
            )

            # Update Deploy row if it exists
            if deploy:
                if event.progress is not None:
                    deploy.progress = int(event.progress)
                if event.stage:
                    deploy.stage = event.stage
                # Update status heuristics
                if event.level == "error":
                    deploy.status = "failed"
                    deploy.error_message = event.message
                elif event.progress == 100:
                    deploy.status = "succeeded"
                    deploy.completed_at = timezone.now()
                else:
                    # If deployment just emitted events and wasn't running, mark pending/running
                    if deploy.status in ("pending", "queued"):
                        deploy.status = "running"
                deploy.save(update_fields=["progress", "stage", "status", "error_message", "completed_at"])

        except Exception:
            # avoid raising from sink — logging would be better but keep silent as logger may call sink
            pass

        # Send to channel layer for live clients
        try:
            payload = {
                "type": "deployment.event",
                "deployment_id": self.deployment_id,
                "stage": event.stage,
                "message": event.message,
                "level": event.level,
                "progress": event.progress,
                "details": event.details or {},
            }
            async_to_sync(self.channel_layer.group_send)(self.group_name, {"type": "deployment.message", "payload": payload})
        except Exception:
            # best-effort; don't raise
            pass
