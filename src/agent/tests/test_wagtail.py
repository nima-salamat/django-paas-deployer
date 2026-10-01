from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.models import Agent, AgentCredential
from agent.wagtail_admin.models import AgentAuditEventViewSet, AgentCredentialViewSet, AgentViewSet


class AgentWagtailTests(TestCase):
    def test_agent_wagtail_viewsets_are_registered(self):
        self.assertIs(AgentViewSet.model, Agent)
        self.assertIs(AgentCredentialViewSet.model, AgentCredential)
        self.assertIsNotNone(AgentAuditEventViewSet.model)

    def test_credential_admin_exposes_metadata_not_secret(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="admin-test-user",
            email="admin-test@example.com",
            password="example-password",
            is_staff=True,
        )
        agent = Agent.objects.create(
            user=user,
            name="admin-agent",
            scopes=["services.read"],
        )
        credential = AgentCredential.objects.create(
            agent=agent,
            token_prefix="pd_agent_test",
            token_hash="0" * 64,
        )
        self.assertFalse(hasattr(credential, "token"))
        self.assertNotIn("hash", str(AgentCredentialViewSet.search_fields).lower())
