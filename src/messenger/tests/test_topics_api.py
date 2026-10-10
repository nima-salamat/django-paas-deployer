from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from messenger.models import Conversation, ConversationParticipant, Message

User = get_user_model()


class MessengerTopicsAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="topics-owner",
            email="topics-owner@example.com",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="topics-member",
            email="topics-member@example.com",
            password="password123",
        )
        self.conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Project team",
            created_by=self.owner,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.owner,
            role=ConversationParticipant.Role.OWNER,
            can_add_members=True,
            can_pin_messages=True,
            can_change_info=True,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.member,
            role=ConversationParticipant.Role.MEMBER,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_creating_topic_converts_group_and_preserves_general_history(self):
        old_message = Message.objects.create(
            conversation=self.conversation,
            sender=self.owner,
            body="Existing General message",
        )
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Deployments"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_forum)
        self.assertTrue(Message.objects.filter(
            pk=old_message.pk,
            conversation=self.conversation,
            body="Existing General message",
        ).exists())

        topic_data = response.data["data"]["topic"]
        topic = Conversation.objects.get(pk=topic_data["id"])
        self.assertEqual(topic.parent_conversation_id, self.conversation.id)
        self.assertEqual(topic.title, "Deployments")
        self.assertEqual(
            set(topic.participants.filter(left_at__isnull=True).values_list("user_id", flat=True)),
            {self.owner.id, self.member.id},
        )

    def test_regular_member_cannot_create_topics(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Private admin topic"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.is_forum)

    def test_root_group_members_added_later_are_added_to_existing_topics(self):
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Operations"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        topic_id = response.data["data"]["topic"]["id"]

        late_member = User.objects.create_user(
            username="topics-late-member",
            email="topics-late@example.com",
            password="password123",
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=late_member,
            role=ConversationParticipant.Role.MEMBER,
        )

        self.assertTrue(ConversationParticipant.objects.filter(
            conversation_id=topic_id,
            user=late_member,
            left_at__isnull=True,
        ).exists())

    def test_topic_conversations_are_hidden_from_top_level_conversation_list(self):
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Deployments"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        listing = self.client.get("/api/messenger/conversations/")
        self.assertEqual(listing.status_code, 200, listing.data)
        payload = listing.data.get("data", {})
        rows = payload.get("results", payload if isinstance(payload, list) else [])
        ids = {row["id"] for row in rows}
        self.assertIn(self.conversation.id, ids)
        self.assertEqual(len(ids), len(rows))
        self.assertTrue(all(row.get("parent_conversation") is None for row in rows))


    def test_root_role_edit_does_not_readd_topic_removed_member(self):
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Restricted"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        topic_id = response.data["data"]["topic"]["id"]

        topic_membership = ConversationParticipant.objects.get(
            conversation_id=topic_id,
            user=self.member,
        )
        topic_membership.left_at = timezone.now()
        topic_membership.save(update_fields=["left_at"])

        root_membership = ConversationParticipant.objects.get(
            conversation=self.conversation,
            user=self.member,
        )
        root_membership.role = ConversationParticipant.Role.ADMIN
        root_membership.save(update_fields=["role"])

        topic_membership.refresh_from_db()
        self.assertIsNotNone(topic_membership.left_at)

    def test_explicit_root_rejoin_restores_topic_membership(self):
        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/topics/",
            {"title": "Rejoin"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        topic_id = response.data["data"]["topic"]["id"]

        root_membership = ConversationParticipant.objects.get(
            conversation=self.conversation,
            user=self.member,
        )
        root_membership.left_at = timezone.now()
        root_membership.save(update_fields=["left_at"])

        topic_membership = ConversationParticipant.objects.get(
            conversation_id=topic_id,
            user=self.member,
        )
        self.assertIsNotNone(topic_membership.left_at)

        root_membership.left_at = None
        root_membership.save(update_fields=["left_at"])

        topic_membership.refresh_from_db()
        self.assertIsNone(topic_membership.left_at)
