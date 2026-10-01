from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from agent.application import begin_idempotency, complete_idempotency
from agent.errors import AgentError
from agent.models import Agent


class AgentIdempotencyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="idempotency-user",
            email="idempotency@example.com",
            password="example-password",
        )
        self.agent = Agent.objects.create(
            user=self.user,
            name="idempotency-agent",
            scopes=["services.create"],
        )

    def test_completed_mutation_replays_exact_response(self):
        factory = APIRequestFactory()
        first_request = factory.post(
            "/agent/v1/services",
            {"name": "example"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="same-operation",
        )
        first_request.user = self.user
        first, replay = begin_idempotency(self.agent, first_request)
        self.assertIsNotNone(first)
        self.assertIsNone(replay)

        complete_idempotency(
            first,
            Response(
                {"result": "success", "service_id": "service-1"},
                status=201,
            ),
        )

        retry_request = factory.post(
            "/agent/v1/services",
            {"name": "example"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="same-operation",
        )
        retry_request.user = self.user
        second, replay = begin_idempotency(self.agent, retry_request)
        self.assertIsNone(second)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.response_body["service_id"], "service-1")

    def test_key_reuse_with_different_request_is_rejected(self):
        factory = APIRequestFactory()
        first_request = factory.post(
            "/agent/v1/services",
            {"name": "first"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="same-key",
        )
        first_request.user = self.user
        row, _ = begin_idempotency(self.agent, first_request)
        complete_idempotency(row, Response({"result": "success"}, status=201))

        second_request = factory.post(
            "/agent/v1/services",
            {"name": "second"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="same-key",
        )
        second_request.user = self.user
        with self.assertRaises(AgentError) as ctx:
            begin_idempotency(self.agent, second_request)
        self.assertEqual(ctx.exception.code, "IDEMPOTENCY_KEY_REUSED")

    def test_sensitive_success_response_can_be_excluded_from_replay_storage(self):
        factory = APIRequestFactory()
        request = factory.post(
            "/agent/v1/services/example/secrets",
            {"key": "DB_PASSWORD", "value": "super-secret"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="secret-key",
        )
        request.user = self.user
        row, _ = begin_idempotency(self.agent, request)
        complete_idempotency(
            row,
            Response(
                {"result": "success", "key": "DB_PASSWORD", "value": "super-secret"},
                status=200,
            ),
            store_body=False,
        )
        row.refresh_from_db()
        self.assertNotIn("super-secret", str(row.response_body))
