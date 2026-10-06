from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent, AgentCredential


class AgentAuthenticationTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username="agent_user",email="agent_user@example.com",password="example-password")
        self.agent=Agent.objects.create(user=self.user,name="agent-one",scopes=["services.read"])
        self.credential,self.raw=issue_access_credential(self.agent)
        self.client=APIClient()

    def test_shared_token_resolver(self):\n        from agent.authentication import authenticate_agent_token\n        agent, user, credential = authenticate_agent_token(self.raw, ip="127.0.0.1")\n        self.assertEqual(agent.pk, self.agent.pk)\n        self.assertEqual(user.pk, self.user.pk)\n        self.assertEqual(credential.pk, self.credential.pk)\n\n    def test_valid_credential(self):
        response=self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["agent_id"],str(self.agent.pk))

    def test_missing_credential(self):
        self.assertEqual(self.client.get("/agent/v1/auth/me").status_code,401)

    def test_invalid_credential(self):
        self.assertEqual(self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION="Bearer invalid").status_code,401)

    def test_expired_credential(self):
        self.credential.expires_at=timezone.now()-timedelta(seconds=1)
        self.credential.save(update_fields=["expires_at","updated_at"])
        self.assertEqual(self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code,401)

    def test_revoked_credential(self):
        self.credential.revoked_at=timezone.now()
        self.credential.save(update_fields=["revoked_at","updated_at"])
        self.assertEqual(self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code,401)

    def test_inactive_user(self):
        self.user.is_active=False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code,401)

    def test_wrong_credential_type(self):
        AgentCredential.objects.create(agent=self.agent,token_prefix="wrong-type",token_hash="0"*64,token_type="other",expires_at=timezone.now()+timedelta(days=1))
        self.assertEqual(self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION="Bearer other").status_code,401)

    def test_plaintext_not_stored(self):
        self.assertNotEqual(self.credential.token_hash,self.raw)
