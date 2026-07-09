from django.db import transaction
from django.utils import timezone

from .models import Deploy, DeployLog, DeploymentStatusChoices, RollbackStatusChoices


RESOURCE_STATUS_FIELDS = {
    "image_build": ("image_status", "building"),
    "network_creation": ("network_status", "creating"),
    "volume_creation": ("volume_status", "creating"),
    "container_creation": ("container_status", "creating"),
    "container_replacement": ("container_status", "replacing"),
    "container_startup": ("container_status", "starting"),
    "health_check": ("health_status", "checking"),
}

STAGE_STATUS_MESSAGES = {
    "deployment_started": "Deployment started.",
    "validation": "Validating deployment.",
    "prepare_resources": "Preparing deployment resources.",
    "image_build": "Building image.",
    "network_creation": "Preparing networks.",
    "volume_creation": "Preparing volumes.",
    "container_creation": "Creating container.",
    "container_startup": "Starting container.",
    "health_check": "Checking health.",
    "rollback": "Rolling back deployment.",
    "cleanup": "Cleaning up resources.",
    "deployment_completed": "Deployment completed.",
    "deployment_failed": "Deployment failed.",
}


class DjangoDeploymentState:
    def __init__(self, deploy: Deploy):
        self.deploy = deploy

    def start(self):
        DeployLog.objects.filter(deploy=self.deploy).delete()
        self._update_deploy(
            status=DeploymentStatusChoices.RUNNING,
            stage="deployment_started",
            progress=0,
            status_message="Deployment started.",
            error_message="",
            rollback_status=RollbackStatusChoices.NOT_REQUIRED,
            health_status="pending",
            container_status="pending",
            image_status="pending",
            volume_status="pending",
            network_status="pending",
            started_at=timezone.now(),
            completed_at=None,
        )

    def event_sink(self, event):
        DeployLog.objects.create(
            deploy=self.deploy,
            service=self.deploy.service,
            stage=event.stage,
            level=event.level,
            message=event.message,
            progress=event.progress,
            details=event.details,
        )

        update = {
            "stage": event.stage,
            "status_message": STAGE_STATUS_MESSAGES.get(event.stage, event.message),
        }
        if event.progress is not None:
            update["progress"] = max(0, min(int(event.progress), 100))

        if event.level == "error":
            update["error_message"] = event.message

        if event.stage in RESOURCE_STATUS_FIELDS:
            field, value = RESOURCE_STATUS_FIELDS[event.stage]
            update[field] = self._resource_value(event, value)

        if event.stage == "deployment_completed":
            update.update(
                {
                    "status": DeploymentStatusChoices.SUCCEEDED,
                    "progress": 100,
                    "completed_at": timezone.now(),
                    "image_status": "built",
                    "network_status": "ready",
                    "volume_status": "ready",
                    "container_status": "running",
                    "health_status": "healthy",
                }
            )

        if event.stage == "rollback":
            update["rollback_status"] = RollbackStatusChoices.PENDING
            update["status"] = DeploymentStatusChoices.ROLLING_BACK

        if event.stage == "deployment_failed":
            update.update(
                {
                    "status": DeploymentStatusChoices.FAILED,
                    "progress": 100,
                    "completed_at": timezone.now(),
                }
            )
            if event.details.get("rollback_performed"):
                update["rollback_status"] = RollbackStatusChoices.SUCCEEDED
            elif self.deploy.rollback_status == RollbackStatusChoices.PENDING:
                update["rollback_status"] = RollbackStatusChoices.FAILED

        self._update_deploy(**update)

    def finish(self, result):
        update = {
            "completed_at": timezone.now(),
            "stage": "deployment_completed" if result.success else (result.stage or "deployment_failed"),
            "status_message": result.message,
            "progress": 100,
            "error_message": "" if result.success else (result.error or result.message),
        }

        if result.success:
            update.update(
                {
                    "status": DeploymentStatusChoices.SUCCEEDED,
                    "rollback_status": RollbackStatusChoices.NOT_REQUIRED,
                    "health_status": "healthy",
                    "container_status": "running",
                    "image_status": "built",
                    "volume_status": "ready",
                    "network_status": "ready",
                }
            )
        else:
            update["status"] = DeploymentStatusChoices.FAILED
            update["rollback_status"] = (
                RollbackStatusChoices.SUCCEEDED if result.rollback_performed else self.deploy.rollback_status
            )

        self._update_deploy(**update)

    def _resource_value(self, event, default):
        if event.stage == "health_check" and event.details.get("container_status"):
            return event.details["container_status"]
        return default

    def _update_deploy(self, **fields):
        with transaction.atomic():
            Deploy.objects.filter(pk=self.deploy.pk).update(**fields)
            for key, value in fields.items():
                setattr(self.deploy, key, value)
