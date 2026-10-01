from datetime import timedelta
import hmac

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent, AgentCredential
from agent.security import token_hash


class AgentAuthenticationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="agent-user", email="agent@example.com", password="test-password")
        self.agent = Agent.objects.create(user=self.user, name="ci-agent", scopes=["services.read"])
        self.credential, self.raw = issue_access_credential(self.agent)
        self.client = APIClient()

    def test_valid_bearer_resolves_agent_context(self):
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["agent_id"], str(self.agent.pk))
        self.assertEqual(response.data["credential"]["prefix"], self.credential.token_prefix)

    def test_missing_credential_is_rejected(self):
        response = self.client.get("/agent/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_invalid_credential_is_rejected(self):
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION="Bearer pd_agent_invalid")
        self.assertEqual(response.status_code, 401)

    def test_expired_credential_is_rejected(self):
        self.credential.expires_at = timezone.now() - timedelta(seconds=1)
        self.credential.save(update_fields=["expires_at", "updated_at"])
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 401)

    def test_revoked_credential_is_rejected(self):
        self.credential.revoked_at = timezone.now()
        self.credential.save(update_fields=["revoked_at", "updated_at"])
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 401)

    def test_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_type_is_rejected(self):
        fake_raw = "pd_agent_wrong_type"
        AgentCredential.objects.create(
            agent=self.agent,
            token_prefix=fake_raw[:20],
            token_hash=token_hash(fake_raw),
            token_type="enrollment",
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get("/agent/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {fake_raw}")
        self.assertEqual(response.status_code, 401)

    def test_token_hash_is_not_plaintext(self):
        self.assertNotEqual(self.credential.token_hash, self.raw)
        self.assertTrue(hmac.compare_digest(self.credential.token_hash, token_hash(self.raw)))
