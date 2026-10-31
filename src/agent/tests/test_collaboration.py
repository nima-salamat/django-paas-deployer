from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.contracts import contract_for, contracts_for_agent
from agent.models import Agent
from agent.scopes import MESSENGER_SCOPES, TICKET_SCOPES, validate_scopes

from messenger.models import Conversation, ConversationParticipant
from tickets.models import Department, Ticket


class AgentCollaborationContractTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="collab-agent-owner",
            email="collab-agent-owner@example.com",
            password="test-password",
        )
        self.agent = Agent.objects.create(
            user=self.user,
            name="collaboration-agent",
            scopes=[
                "messenger.conversations.read",
                "messenger.messages.read",
                "messenger.messages.send",
                "messenger.groups.search",
                "messenger.groups.join",
                "messenger.permissions.manage",
                "tickets.read",
                "tickets.create",
                "tickets.reply",
            ],
        )
        _, self.token = issue_access_credential(self.agent)
        self.client = APIClient()

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_messenger_and_ticket_scopes_are_registered(self):
        accepted = validate_scopes(
            ["messenger.messages.send", "messenger.permissions.manage", "tickets.create"]
        )
        self.assertEqual(
            accepted,
            ["messenger.messages.send", "messenger.permissions.manage", "tickets.create"],
        )
        self.assertTrue(set(MESSENGER_SCOPES).issubset(set(validate_scopes(MESSENGER_SCOPES))))
        self.assertTrue(set(TICKET_SCOPES).issubset(set(validate_scopes(TICKET_SCOPES))))

    def test_contracts_cover_messenger_and_ticket_routes(self):
        expected = {
            ("GET", "/agent/v1/messenger/users/search"),
            ("POST", "/agent/v1/messenger/conversations"),
            ("GET", "/agent/v1/messenger/conversations/{conversation_id}/messages"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/messages"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/members/{user_id}/permissions"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/join-requests/{request_id}/action"),
            ("GET", "/agent/v1/tickets"),
            ("POST", "/agent/v1/tickets"),
            ("GET", "/agent/v1/tickets/{ticket_id}"),
            ("POST", "/agent/v1/tickets/{ticket_id}/messages"),
            ("POST", "/agent/v1/tickets/{ticket_id}/close"),
        }
        for method, path in expected:
            self.assertIsNotNone(contract_for(path, method), (method, path))

        enabled = {
            (item.method, item.path) for item in contracts_for_agent(self.agent)
        }
        self.assertIn(("GET", "/agent/v1/messenger/conversations/{conversation_id}/messages"), enabled)
        self.assertIn(("POST", "/agent/v1/tickets/{ticket_id}/messages"), enabled)
        self.assertNotIn(("DELETE", "/agent/v1/messenger/messages/{message_id}"), enabled)

    def test_encrypted_conversations_are_excluded_from_agent_chat_list(self):
        normal = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=normal,
            user=self.user,
            role=ConversationParticipant.Role.OWNER,
        )
        encrypted = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            security_mode=Conversation.SecurityMode.MATRIX_E2EE,
            matrix_room_id=f"!{uuid4().hex}:matrix.example",
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=encrypted,
            user=self.user,
            role=ConversationParticipant.Role.OWNER,
        )

        response = self.client.get("/agent/v1/messenger/conversations", **self.auth())
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(normal.pk, ids)
        self.assertNotIn(encrypted.pk, ids)
        self.assertEqual(response.data["security_mode"], "standard")

    def test_encrypted_message_read_is_explicitly_rejected(self):
        encrypted = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            security_mode=Conversation.SecurityMode.MATRIX_E2EE,
            matrix_room_id=f"!{uuid4().hex}:matrix.example",
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=encrypted,
            user=self.user,
            role=ConversationParticipant.Role.OWNER,
        )
        response = self.client.get(
            f"/agent/v1/messenger/conversations/{encrypted.pk}/messages",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["code"], "UNSUPPORTED_SECURITY_MODE")

    def test_ticket_read_is_limited_to_linked_user_owned_records(self):
        department = Department.objects.create(name="Agent Support")
        own_ticket = Ticket.objects.create(
            user=self.user,
            department=department,
            subject="My own ticket",
        )
        response = self.client.get(
            f"/agent/v1/tickets/{own_ticket.pk}",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)

        other = get_user_model().objects.create_user(
            username="other-ticket-owner",
            email="other-ticket-owner@example.com",
            password="test-password",
        )
        other_ticket = Ticket.objects.create(
            user=other,
            department=department,
            subject="Someone else's ticket",
        )
        response = self.client.get(
            f"/agent/v1/tickets/{other_ticket.pk}",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 404)
