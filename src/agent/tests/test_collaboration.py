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
            ("DELETE", "/agent/v1/messenger/conversations/{conversation_id}"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/clear-history"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/invite-links"),
            ("DELETE", "/agent/v1/messenger/conversations/{conversation_id}/invite-links/{link_id}"),
            ("POST", "/agent/v1/messenger/join"),
            ("GET", "/agent/v1/messenger/me/join-requests"),
            ("DELETE", "/agent/v1/messenger/join-requests/{request_id}"),
            ("POST", "/agent/v1/messenger/messages/{message_id}/forward"),
            ("DELETE", "/agent/v1/messenger/messages/{message_id}/react"),
            ("PUT", "/agent/v1/messenger/messages/{message_id}/pin"),
            ("DELETE", "/agent/v1/messenger/messages/{message_id}/pin"),
            ("GET", "/agent/v1/messenger/conversations/{conversation_id}/pinned-messages"),
            ("GET", "/agent/v1/messenger/conversations/{conversation_id}/messages"),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/messages"),
            ("PATCH", "/agent/v1/messenger/conversations/{conversation_id}/members/{user_id}/permissions"),
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

    def test_new_messenger_operations_have_separate_least_privilege_scopes(self):
        expected = {
            ("POST", "/agent/v1/messenger/join"): ("messenger.invites.join",),
            ("GET", "/agent/v1/messenger/me/join-requests"): ("messenger.join_requests.own.read",),
            ("DELETE", "/agent/v1/messenger/join-requests/{request_id}"): ("messenger.join_requests.own.cancel",),
            ("POST", "/agent/v1/messenger/messages/{message_id}/forward"): (
                "messenger.messages.read", "messenger.messages.send", "messenger.messages.forward",
            ),
            ("DELETE", "/agent/v1/messenger/conversations/{conversation_id}"): (
                "messenger.conversations.delete",
            ),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/clear-history"): (
                "messenger.conversations.history.clear",
            ),
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/invite-links"): (
                "messenger.invites.create",
            ),
            ("DELETE", "/agent/v1/messenger/conversations/{conversation_id}/invite-links/{link_id}"): (
                "messenger.invites.revoke",
            ),
        }
        for (method, path), scopes in expected.items():
            contract = contract_for(path, method)
            self.assertIsNotNone(contract, (method, path))
            self.assertEqual(contract.scopes, scopes)
        all_new_scopes = {scope for scopes in expected.values() for scope in scopes}
        self.assertTrue(all_new_scopes.issubset(set(validate_scopes(all_new_scopes))))

    def test_high_impact_chat_cleanup_requires_explicit_dedicated_scope(self):
        self.assertEqual(
            contract_for("/agent/v1/messenger/conversations/{conversation_id}", "DELETE").scopes,
            ("messenger.conversations.delete",),
        )
        self.assertEqual(
            contract_for("/agent/v1/messenger/conversations/{conversation_id}/clear-history", "POST").scopes,
            ("messenger.conversations.history.clear",),
        )
        enabled = {(item.method, item.path) for item in contracts_for_agent(self.agent)}
        self.assertNotIn(
            ("DELETE", "/agent/v1/messenger/conversations/{conversation_id}"),
            enabled,
        )
        self.assertNotIn(
            ("POST", "/agent/v1/messenger/conversations/{conversation_id}/clear-history"),
            enabled,
        )

    def test_new_messenger_operations_are_denied_without_their_scopes(self):
        response = self.client.get(
            "/agent/v1/messenger/me/join-requests",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")
        self.assertIn(
            "messenger.join_requests.own.read",
            response.data["missing_scopes"],
        )

        response = self.client.delete(
            "/agent/v1/messenger/conversations/999",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")
        self.assertIn(
            "messenger.conversations.delete",
            response.data["missing_scopes"],
        )

    def test_forward_respects_target_group_admin_only_posting_policy(self):
        from messenger.models import Message

        self.agent.scopes = [
            "messenger.messages.read",
            "messenger.messages.send",
            "messenger.messages.forward",
        ]
        self.agent.save(update_fields=["scopes", "updated_at"])

        source = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=source,
            user=self.user,
            role=ConversationParticipant.Role.OWNER,
        )
        other_owner = get_user_model().objects.create_user(
            username="forward-target-owner",
            email="forward-target-owner@example.com",
            password="test-password",
        )
        target = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            created_by=other_owner,
            only_admins_send=True,
        )
        ConversationParticipant.objects.create(
            conversation=target,
            user=other_owner,
            role=ConversationParticipant.Role.OWNER,
        )
        ConversationParticipant.objects.create(
            conversation=target,
            user=self.user,
            role=ConversationParticipant.Role.MEMBER,
        )
        message = Message.objects.create(
            conversation=source,
            sender=self.user,
            body="Please forward this message",
        )

        response = self.client.post(
            f"/agent/v1/messenger/messages/{message.pk}/forward",
            {"conversation_id": target.pk},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "PERMISSION_DENIED")
        self.assertFalse(
            Message.objects.filter(
                conversation=target,
                forwarded_from_message=message,
            ).exists()
        )

    def test_reaction_delete_removes_only_the_agent_users_reaction(self):
        from messenger.models import Message, MessageReaction

        self.agent.scopes = ["messenger.messages.reactions.remove"]
        self.agent.save(update_fields=["scopes", "updated_at"])
        other = get_user_model().objects.create_user(
            username="reaction-owner",
            email="reaction-owner@example.com",
            password="test-password",
        )
        conv = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=conv,
            user=self.user,
            role=ConversationParticipant.Role.OWNER,
        )
        ConversationParticipant.objects.create(
            conversation=conv,
            user=other,
            role=ConversationParticipant.Role.MEMBER,
        )
        message = Message.objects.create(
            conversation=conv,
            sender=other,
            body="React to this",
        )
        own_reaction = MessageReaction.objects.create(
            message=message, user=self.user, emoji="👍"
        )
        other_reaction = MessageReaction.objects.create(
            message=message, user=other, emoji="👍"
        )

        response = self.client.delete(
            f"/agent/v1/messenger/messages/{message.pk}/react",
            {"emoji": "👍"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["action"], "removed")
        self.assertFalse(MessageReaction.objects.filter(pk=own_reaction.pk).exists())
        self.assertTrue(MessageReaction.objects.filter(pk=other_reaction.pk).exists())

        # DELETE is idempotent: repeating it must not create a new reaction.
        response = self.client.delete(
            f"/agent/v1/messenger/messages/{message.pk}/react",
            {"emoji": "👍"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["action"], "unchanged")
        self.assertEqual(MessageReaction.objects.filter(message=message).count(), 1)

    def test_message_pin_unpin_and_pinned_list(self):
        from messenger.models import Message, PinnedMessage

        self.agent.scopes = [
            "messenger.messages.pin",
            "messenger.messages.unpin",
            "messenger.messages.pinned.read",
        ]
        self.agent.save(update_fields=["scopes", "updated_at"])

        owner = get_user_model().objects.create_user(
            username="pin-group-owner",
            email="pin-group-owner@example.com",
            password="test-password",
        )
        conv = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Pinned messages test",
            created_by=owner,
            history_visibility=Conversation.HistoryVisibility.FROM_JOIN,
        )
        ConversationParticipant.objects.create(
            conversation=conv,
            user=owner,
            role=ConversationParticipant.Role.OWNER,
        )
        member = ConversationParticipant.objects.create(
            conversation=conv,
            user=self.user,
            role=ConversationParticipant.Role.MEMBER,
            can_pin_messages=False,
        )
        message = Message.objects.create(
            conversation=conv,
            sender=owner,
            body="Important pinned message",
        )

        response = self.client.put(
            f"/agent/v1/messenger/messages/{message.pk}/pin",
            {},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PinnedMessage.objects.filter(message=message).exists())

        member.can_pin_messages = True
        member.save(update_fields=["can_pin_messages"])
        response = self.client.put(
            f"/agent/v1/messenger/messages/{message.pk}/pin",
            {},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["pinned"])
        self.assertTrue(PinnedMessage.objects.filter(message=message).exists())

        # PUT is idempotent and leaves the message pinned on retry.
        response = self.client.put(
            f"/agent/v1/messenger/messages/{message.pk}/pin",
            {},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["changed"])
        self.assertEqual(PinnedMessage.objects.filter(conversation=conv).count(), 1)

        response = self.client.get(
            f"/agent/v1/messenger/conversations/{conv.pk}/pinned-messages",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["message"]["id"], message.pk)

        response = self.client.delete(
            f"/agent/v1/messenger/messages/{message.pk}/pin",
            {},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["pinned"])
        self.assertFalse(PinnedMessage.objects.filter(message=message).exists())

        response = self.client.get(
            f"/agent/v1/messenger/conversations/{conv.pk}/pinned-messages",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_reaction_pin_and_pinned_read_have_independent_scopes(self):
        expected = {
            ("DELETE", "/agent/v1/messenger/messages/{message_id}/react"): (
                "messenger.messages.reactions.remove",
            ),
            ("PUT", "/agent/v1/messenger/messages/{message_id}/pin"): (
                "messenger.messages.pin",
            ),
            ("DELETE", "/agent/v1/messenger/messages/{message_id}/pin"): (
                "messenger.messages.unpin",
            ),
            ("GET", "/agent/v1/messenger/conversations/{conversation_id}/pinned-messages"): (
                "messenger.messages.pinned.read",
            ),
        }
        for (method, path), scopes in expected.items():
            contract = contract_for(path, method)
            self.assertIsNotNone(contract, (method, path))
            self.assertEqual(contract.scopes, scopes)
        all_scopes = {scope for scopes in expected.values() for scope in scopes}
        self.assertTrue(all_scopes.issubset(set(validate_scopes(all_scopes))))

        self.agent.scopes = []
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.delete(
            "/agent/v1/messenger/messages/999/react",
            {"emoji": "👍"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "messenger.messages.reactions.remove",
            response.data["missing_scopes"],
        )

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
