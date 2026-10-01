from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.models import Agent, AgentCredential
from agent.wagtail_admin.models import (
    AgentAuditEventViewSet,
    AgentCredentialViewSet,
    AgentManagementPolicy,
    AgentViewSet,
)


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


    def test_agent_cannot_be_deleted_directly_from_wagtail(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username="wagtail-policy-user",
            email="wagtail-policy@example.com",
            password="example-password",
            is_staff=True,
        )
        policy = AgentManagementPolicy(Agent)
        self.assertFalse(policy.user_has_permission(user, "delete"))

    def test_disabled_agent_can_be_enabled_but_revoked_agent_cannot(self):
        from agent.application import set_agent_status
        User = get_user_model()
        user = User.objects.create_user(
            username="agent-state-user",
            email="agent-state@example.com",
            password="example-password",
        )
        agent = Agent.objects.create(
            user=user,
            name="state-agent",
            scopes=["services.read"],
        )
        agent = set_agent_status(agent, Agent.Status.DISABLED)
        self.assertEqual(agent.status, Agent.Status.DISABLED)
        agent = set_agent_status(agent, Agent.Status.ACTIVE)
        self.assertEqual(agent.status, Agent.Status.ACTIVE)
        agent = set_agent_status(agent, Agent.Status.REVOKED)
        from agent.errors import AgentError
        with self.assertRaises(AgentError):
            set_agent_status(agent, Agent.Status.ACTIVE)
