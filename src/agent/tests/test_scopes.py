from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agent.application import exchange_enrollment, issue_access_credential
from agent.errors import AgentError
from agent.models import Agent, AgentAuditEvent, AgentEnrollmentToken
from agent.scopes import ALL_SCOPES, DEFAULT_SCOPES
from agent.security import sanitize_metadata, token_hash


class AgentScopeTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username="scope_user",email="scope_user@example.com",password="example-password")
        self.agent=Agent.objects.create(user=self.user,name="scope-agent",scopes=["services.read"])
        self.credential,self.raw=issue_access_credential(self.agent)
        self.client=APIClient()

    def test_mutation_without_scope_is_denied(self):
        response=self.client.post("/agent/v1/services",{"name":"x"},format="json",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.data["code"],"INSUFFICIENT_SCOPE")

    def test_capability_document_matches_agent_scopes(self):
        response=self.client.get("/agent/v1/capabilities",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["scopes"],["services.read"])
        self.assertTrue(response.data["capabilities"]["services"]["read"])
        self.assertFalse(response.data["capabilities"]["services"]["create"])

    def test_defaults_are_subset_of_known_scopes(self):
        self.assertTrue(set(DEFAULT_SCOPES)<=set(ALL_SCOPES))
        self.assertNotIn("shell.execute",DEFAULT_SCOPES)
        self.assertNotIn("services.delete",DEFAULT_SCOPES)

    def test_enrollment_is_single_use(self):
        value="pd_enroll_example_value"
        row=AgentEnrollmentToken.objects.create(
            agent=self.agent,token_prefix=value[:20],token_hash=token_hash(value),
            expires_at=timezone.now()+timedelta(minutes=5),
        )
        agent,credential,access=exchange_enrollment(value)
        self.assertEqual(agent.pk,self.agent.pk)
        self.assertTrue(access.startswith("pd_agent_"))
        row.refresh_from_db()
        self.assertIsNotNone(row.used_at)
        with self.assertRaises(AgentError) as ctx:
            exchange_enrollment(value)
        self.assertEqual(ctx.exception.code,"ENROLLMENT_EXPIRED")
        self.assertTrue(credential.pk)

    def test_expired_enrollment_fails(self):
        value="pd_enroll_expired_value"
        AgentEnrollmentToken.objects.create(
            agent=self.agent,token_prefix=value[:20],token_hash=token_hash(value),
            expires_at=timezone.now()-timedelta(seconds=1),
        )
        with self.assertRaises(AgentError) as ctx:
            exchange_enrollment(value)
        self.assertEqual(ctx.exception.code,"ENROLLMENT_EXPIRED")

    def test_generated_manifest_contains_bootstrap_but_not_access_token(self):
        response=self.client.get("/agent/v1/agent.md",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code,200)
        body=response.content.decode()
        self.assertIn("PASSDEPLOYER_ENROLLMENT_TOKEN",body)
        self.assertIn(str(self.agent.pk),body)
        self.assertNotIn(self.raw,body)

    def test_audit_metadata_is_not_token_material(self):
        self.client.get("/agent/v1/auth/me",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        event=AgentAuditEvent.objects.filter(agent=self.agent).first()
        self.assertIsNotNone(event)
        self.assertNotIn(self.raw,str(event.metadata))

    def test_sensitive_metadata_is_redacted(self):
        result=sanitize_metadata({"token":"secret-value","nested":{"password":"pw","safe":"ok"}})
        self.assertEqual(result["token"],"[REDACTED]")
        self.assertEqual(result["nested"]["password"],"[REDACTED]")
        self.assertEqual(result["nested"]["safe"],"ok")
