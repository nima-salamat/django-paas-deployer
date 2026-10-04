from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deploy.models import Deploy, DeploymentStatusChoices
from deployments.common.deadline import DeploymentDeadline
from deployments.core.state.manager import StateManager
from plans.models import Plan
from services.models import Service
from users.models import User


class ReusedDeploymentDeadlineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reused-deploy-deadline",
            email="reused-deploy-deadline@example.invalid",
            password="test-password",
        )
        self.plan = Plan.objects.create(
            name="Reused Deploy Bronze",
            platform="docker",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
        )
        self.service = Service.objects.create(
            name="reused-deploy-deadline-service",
            user=self.user,
            plan=self.plan,
        )

    def test_queueing_reused_deploy_clears_all_lifecycle_deadline_timestamps(self):
        old = timezone.now() - timedelta(hours=2)
        deploy = Deploy.objects.create(
            name="reused-deploy-deadline",
            service=self.service,
            created_by=self.user,
            status=DeploymentStatusChoices.SUCCEEDED,
            stage="starting",
            started_at=old,
            completed_at=old,
            base_image_wait_started_at=old,
            base_image_ready_at=old,
            application_started_at=old,
            worker_heartbeat_at=old,
        )

        StateManager.transition_deploy(
            deploy.pk,
            DeploymentStatusChoices.PENDING,
            update_fields={
                "stage": "queued",
                "progress": 0,
                "status_message": "Rebuild queued.",
                "error_message": "",
                "cancel_requested": False,
            },
        )

        deploy.refresh_from_db()
        assert deploy.status == DeploymentStatusChoices.PENDING
        assert deploy.started_at is None
        assert deploy.completed_at is None
        assert deploy.worker_heartbeat_at is None
        assert deploy.base_image_wait_started_at is None
        assert deploy.base_image_ready_at is None
        assert deploy.application_started_at is None
        assert DeploymentDeadline.from_deployment(deploy).deadline is None

    def test_execution_claim_starts_a_fresh_deadline_after_legacy_stale_timestamps(self):
        old = timezone.now() - timedelta(hours=2)
        self.service.status = SERVICE_STATUS_CHOICES.QUEUED
        self.service.save(update_fields=["status", "updated_at"])

        deploy = Deploy.objects.create(
            name="reused-deploy-claim",
            service=self.service,
            created_by=self.user,
            status=DeploymentStatusChoices.PENDING,
            stage="queued",
            started_at=None,
            completed_at=None,
            base_image_wait_started_at=old,
            base_image_ready_at=old,
            application_started_at=old,
            worker_heartbeat_at=None,
        )

        claimed_at = timezone.now()
        claimed = StateManager.lock_and_get_deployment(
            deploy.pk,
            task_id="fresh-worker-owner",
        )

        assert claimed.status == DeploymentStatusChoices.RUNNING
        assert claimed.started_at is not None
        assert claimed.started_at >= claimed_at
        assert claimed.completed_at is None
        assert claimed.base_image_wait_started_at is None
        assert claimed.base_image_ready_at is None
        assert claimed.application_started_at is None

        deadline = DeploymentDeadline.from_deployment(claimed)
        assert deadline.deadline is not None
        assert deadline.deadline > timezone.now()
