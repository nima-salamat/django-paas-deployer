from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from agent.models import Agent, AgentAuditEvent, AgentCredential, AgentEnrollmentToken, AgentIdempotencyRecord
from users.models import User


class AgentUserDeletionTests(TestCase):
    def test_agent_credentials_and_idempotency_are_deleted_but_audit_is_retained(self):
        user = User.objects.create_user(
            username="agent-delete",
            email="agent-delete@example.invalid",
        )
        agent = Agent.objects.create(user=user, name="deploy-agent")
        credential = AgentCredential.objects.create(
            agent=agent,
            token_prefix="agt",
            token_hash="a" * 64,
        )
        enrollment = AgentEnrollmentToken.objects.create(
            agent=agent,
            token_prefix="enroll",
            token_hash="b" * 64,
            expires_at=timezone.now() + timedelta(days=3650),
        )
        idem = AgentIdempotencyRecord.objects.create(
            agent=agent,
            key="delete-test",
            method="POST",
            path="/agent/v1/test",
            request_hash="c" * 64,
            expires_at="2099-01-01T00:00:00Z",
        )
        audit = AgentAuditEvent.objects.create(
            agent=agent,
            user=user,
            action="delete-test",
            request_id="req-delete",
        )

        user.delete()

        self.assertFalse(Agent.objects.filter(pk=agent.pk).exists())
        self.assertFalse(AgentCredential.objects.filter(pk=credential.pk).exists())
        self.assertFalse(AgentEnrollmentToken.objects.filter(pk=enrollment.pk).exists())
        self.assertFalse(AgentIdempotencyRecord.objects.filter(pk=idem.pk).exists())

        audit.refresh_from_db()
        self.assertIsNone(audit.user_id)
        self.assertIsNone(audit.agent_id)
