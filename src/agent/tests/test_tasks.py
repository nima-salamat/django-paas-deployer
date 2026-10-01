from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from agent.models import Agent, AgentEnrollmentToken, AgentIdempotencyRecord
from agent.security import token_hash
from agent.tasks import cleanup_expired_state


class AgentMaintenanceTaskTests(TestCase):
    def test_cleanup_removes_expired_ephemeral_state(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="cleanup-user",
            email="cleanup@example.com",
            password="example-password",
        )
        agent = Agent.objects.create(
            user=user,
            name="cleanup-agent",
            scopes=["services.read"],
        )
        expired = timezone.now() - timedelta(minutes=1)
        AgentEnrollmentToken.objects.create(
            agent=agent,
            token_prefix="pd_enroll_expired",
            token_hash=token_hash("pd_enroll_expired"),
            expires_at=expired,
        )
        AgentIdempotencyRecord.objects.create(
            agent=agent,
            key="expired-key",
            method="POST",
            path="/agent/v1/services",
            request_hash="0" * 64,
            state=AgentIdempotencyRecord.State.COMPLETE,
            status_code=201,
            response_body={"result": "success"},
            expires_at=expired,
        )
        result = cleanup_expired_state()
        self.assertEqual(result["enrollment_deleted"], 1)
        self.assertEqual(result["idempotency_deleted"], 1)
