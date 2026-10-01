from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from agent.application import begin_idempotency, complete_idempotency, redact_shell_result
from agent.models import Agent, AgentIdempotencyRecord
from agent.security import sanitize_metadata


class AgentIdempotencySecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="idem-user", email="idem@example.com", password="test")
        self.agent = Agent.objects.create(user=self.user, name="idem-agent", scopes=["services.create"])

    @override_settings(CACHES={"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache"}})
    def test_same_idempotency_key_replays_completed_response(self):
        factory = APIRequestFactory()
        request = factory.post("/agent/v1/services", {"name":"x"}, format="json")
        request.user = self.user
        first, replay = begin_idempotency(self.agent, request)
        self.assertIsNotNone(first)
        self.assertIsNone(replay)

        from rest_framework.response import Response
        complete_idempotency(first, Response({"result":"success","service_id":"abc"}, status=201))

        second_request = factory.post("/agent/v1/services", {"name":"x"}, format="json", HTTP_IDEMPOTENCY_KEY=first.key)
        second_request.user = self.user
        second_request.agent = self.agent
        # APIRequestFactory header is available via request.headers.
        second, replay = begin_idempotency(self.agent, second_request)
        self.assertIsNone(second)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.response_body["service_id"], "abc")

    def test_same_idempotency_key_cannot_change_request_shape(self):
        factory = APIRequestFactory()
        request = factory.post("/agent/v1/services", {"name":"x"}, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
        request.user = self.user
        first, _ = begin_idempotency(self.agent, request)
        from rest_framework.response import Response
        complete_idempotency(first, Response({"result":"success"}, status=201))
        second_request = factory.post("/agent/v1/services", {"name":"different"}, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
        second_request.user = self.user
        with self.assertRaises(Exception) as ctx:
            begin_idempotency(self.agent, second_request)
        self.assertEqual(getattr(ctx.exception, "code", ""), "IDEMPOTENCY_KEY_REUSED")

    def test_sensitive_metadata_is_redacted(self):
        data = sanitize_metadata({"token":"secret","nested":{"password":"pw","safe":"ok"}})
        self.assertEqual(data["token"], "[REDACTED]")
        self.assertEqual(data["nested"]["password"], "[REDACTED]")
        self.assertEqual(data["nested"]["safe"], "ok")
