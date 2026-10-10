from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from messenger.models import Conversation, ConversationParticipant, Message, MessageAttachment

User = get_user_model()


class MessengerSecurityModeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="secure-mode-owner",
            email="secure-mode-owner@example.com",
            password="password123",
        )
        self.peer = User.objects.create_user(
            username="secure-mode-peer",
            email="secure-mode-peer@example.com",
            password="password123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def make_encrypted_group(self):
        conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Encrypted group",
            created_by=self.owner,
            security_mode=Conversation.SecurityMode.MATRIX_E2EE,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=self.owner,
            role=ConversationParticipant.Role.OWNER,
            can_send_messages=True,
            can_send_media=True,
            can_change_info=True,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=self.peer,
        )
        return conversation

    def test_new_conversations_default_to_standard_mode(self):
        conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Normal group",
            created_by=self.owner,
        )
        self.assertEqual(conversation.security_mode, Conversation.SecurityMode.STANDARD)

    def test_security_mode_cannot_be_changed_after_creation(self):
        conversation = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.owner,
        )
        conversation.security_mode = Conversation.SecurityMode.MATRIX_E2EE
        with self.assertRaises(ValidationError):
            conversation.save()

        conversation.refresh_from_db()
        self.assertEqual(conversation.security_mode, Conversation.SecurityMode.STANDARD)

    def test_plaintext_messages_are_rejected_for_encrypted_conversation(self):
        conversation = self.make_encrypted_group()
        with self.assertRaisesMessage(
            ValidationError,
            "Plaintext Messenger messages are disabled for encrypted conversations.",
        ):
            Message.objects.create(
                conversation=conversation,
                sender=self.owner,
                body="This must never be stored as plaintext",
            )
        self.assertFalse(Message.objects.filter(conversation=conversation).exists())

    def test_legacy_django_media_is_rejected_for_encrypted_conversation(self):
        conversation = self.make_encrypted_group()
        with self.assertRaisesMessage(
            ValidationError,
            "Django attachments are disabled for encrypted conversations.",
        ):
            MessageAttachment.objects.create(
                conversation=conversation,
                uploaded_by=self.owner,
                file=SimpleUploadedFile("secret.txt", b"plaintext file bytes"),
                original_filename="secret.txt",
                content_type="text/plain",
                size=20,
                kind=MessageAttachment.Kind.FILE,
            )
        self.assertFalse(MessageAttachment.objects.filter(conversation=conversation).exists())

    def test_request_for_secure_dm_fails_closed_without_creating_normal_dm(self):
        before = Conversation.objects.filter(
            type=Conversation.Type.PRIVATE,
            participants__user=self.owner,
        ).distinct().count()
        response = self.client.post(
            "/api/messenger/conversations/",
            {
                "type": "private",
                "user_id": self.peer.id,
                "security_mode": Conversation.SecurityMode.MATRIX_E2EE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 503, response.data)
        self.assertIn("No conversation was created", response.data["message"])
        after = Conversation.objects.filter(
            type=Conversation.Type.PRIVATE,
            participants__user=self.owner,
        ).distinct().count()
        self.assertEqual(after, before)

    def test_request_for_secure_group_fails_closed_without_creating_normal_group(self):
        response = self.client.post(
            "/api/messenger/conversations/",
            {
                "type": "group",
                "title": "Must not downgrade",
                "security_mode": Conversation.SecurityMode.MATRIX_E2EE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 503, response.data)
        self.assertFalse(
            Conversation.objects.filter(title="Must not downgrade").exists()
        )

    def test_encrypted_group_topics_cannot_fall_back_to_plaintext_conversations(self):
        conversation = self.make_encrypted_group()

        get_response = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/topics/"
        )
        self.assertEqual(get_response.status_code, 409, get_response.data)

        post_response = self.client.post(
            f"/api/messenger/conversations/{conversation.id}/topics/",
            {"title": "Plaintext child"},
            format="json",
        )
        self.assertEqual(post_response.status_code, 409, post_response.data)
        self.assertFalse(
            Conversation.objects.filter(parent_conversation=conversation).exists()
        )
