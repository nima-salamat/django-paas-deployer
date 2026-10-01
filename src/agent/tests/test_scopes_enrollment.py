from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agent.application import exchange_enrollment, issue_access_credential
from agent.models import Agent, AgentAuditEvent, AgentEnrollmentToken
from agent.scopes import DEFAULT_SCOPES, ALL_SCOPES
from agent.security import token_hash


class AgentScopeAndEnrollmentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="scope-user", email="scope@example.com", password="test-password")
        self.agent = Agent.objects.create(user=self.user, name="scope-agent", scopes=["services.read", "agent.manifest.generate"])
        self.credential, self.raw = issue_access_credential(self.agent)
        self.client = APIClient()

    def test_scope_denies_mutation(self):
        response = self.client.post(
            "/agent/v1/services",
            {"name": "nope", "plan": "00000000-0000-0000-0000-000000000001", "network": "00000000-0000-0000-0000-000000000002"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")

    def test_capabilities_reflect_only_agent_scopes(self):
        response = self.client.get("/agent/v1/capabilities", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scopes"], ["agent.manifest.generate", "services.read"])
        self.assertTrue(response.data["capabilities"]["services"]["read"])
        self.assertFalse(response.data["capabilities"]["services"]["create"])

    def test_default_scopes_are_safe_and_known(self):
        self.assertTrue(set(DEFAULT_SCOPES) <= set(ALL_SCOPES))
        self.assertNotIn("services.delete", DEFAULT_SCOPES)
        self.assertNotIn("shell.execute", DEFAULT_SCOPES)

    def test_enrollment_exchange_is_one_time(self):
        enrollment = "pd_enroll_test-token"
        row = AgentEnrollmentToken.objects.create(
            agent=self.agent,
            token_prefix=enrollment[:20],
            token_hash=token_hash(enrollment),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        agent, credential, access = exchange_enrollment(enrollment)
        self.assertEqual(agent.pk, self.agent.pk)
        self.assertTrue(access.startswith("pd_agent_"))
        row.refresh_from_db()
        self.assertIsNotNone(row.used_at)
        with self.assertRaises(Exception) as ctx:
            exchange_enrollment(enrollment)
        self.assertEqual(getattr(ctx.exception, "code", ""), "ENROLLMENT_EXPIRED")
        self.assertTrue(AgentCredential.objects.filter(pk=credential.pk).exists())

    def test_expired_enrollment_cannot_exchange(self):
        enrollment = "pd_enroll_expired"
        AgentEnrollmentToken.objects.create(
            agent=self.agent,
            token_prefix=enrollment[:20],
            token_hash=token_hash(enrollment),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(Exception) as ctx:
            exchange_enrollment(enrollment)
        self.assertEqual(getattr(ctx.exception, "code", ""), "ENROLLMENT_EXPIRED")

    def test_manifest_contains_short_lived_enrollment_but_not_permanent_access_token(self):
        response = self.client.get("/agent/v1/agent.md", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("PASSDEPLOYER_ENROLLMENT_TOKEN", body)
        self.assertIn(str(self.agent.pk), body)
        self.assertNotIn(self.raw, body)

    def test_agent_audit_records_are_sanitized(self):
        self.client.get(
            "/agent/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            HTTP_X_REQUEST_ID="12345678-1234-4234-8234-123456789012",
        )
        event = AgentAuditEvent.objects.filter(agent=self.agent).first()
        self.assertIsNotNone(event)
        self.assertNotIn(self.raw, event.metadata.values())
