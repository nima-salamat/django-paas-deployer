from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from cryptography.fernet import Fernet
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from messenger.models import Contact, Conversation, ConversationParticipant, MatrixDevice, Message, MessageAttachment

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
            matrix_room_id=f"!secure-group-{self.owner.pk}-{self.peer.pk}:matrix.example.test",
            matrix_space_id=f"!secure-space-{self.owner.pk}-{self.peer.pk}:matrix.example.test",
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
        conversation.matrix_room_id = f"!immutable-{self.owner.pk}:matrix.example.test"
        with self.assertRaisesMessage(ValidationError, "security mode and Matrix room bindings are immutable"):
            conversation.save()

        conversation.refresh_from_db()
        self.assertEqual(conversation.security_mode, Conversation.SecurityMode.STANDARD)
        self.assertIsNone(conversation.matrix_room_id)

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


    def test_standard_conversation_api_exposes_standard_security_mode(self):
        response = self.client.post(
            "/api/messenger/conversations/",
            {"type": "group", "title": "Normal by default"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["data"]["security_mode"],
            Conversation.SecurityMode.STANDARD,
        )

    def test_legacy_message_read_write_and_search_routes_reject_encrypted_rooms(self):
        conversation = self.make_encrypted_group()

        history = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/messages/"
        )
        self.assertEqual(history.status_code, 409, history.data)

        send = self.client.post(
            f"/api/messenger/conversations/{conversation.id}/messages/",
            {"body": "must not fall back to plaintext"},
            format="json",
        )
        self.assertEqual(send.status_code, 409, send.data)

        search = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/messages/search/?q=old"
        )
        self.assertEqual(search.status_code, 409, search.data)
        self.assertFalse(Message.objects.filter(conversation=conversation).exists())

    def test_legacy_detail_event_and_call_routes_reject_encrypted_rooms(self):
        conversation = self.make_encrypted_group()

        # Metadata remains readable so the UI can explain that Matrix is not
        # configured, but server-side message previews/drafts stay hidden.
        detail = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/"
        )
        self.assertEqual(detail.status_code, 200, detail.data)
        detail_data = detail.data["data"]
        self.assertEqual(detail_data["security_mode"], Conversation.SecurityMode.MATRIX_E2EE)
        self.assertIsNone(detail_data["last_message"])
        self.assertEqual(detail_data["draft_text"], "")

        events = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/events/"
        )
        self.assertEqual(events.status_code, 409, events.data)

        call = self.client.post(
            f"/api/messenger/conversations/{conversation.id}/call/",
            {"video": False, "audio": True},
            format="json",
        )
        self.assertEqual(call.status_code, 409, call.data)


    def test_server_side_composer_drafts_are_rejected_for_encrypted_rooms(self):
        conversation = self.make_encrypted_group()
        participant = ConversationParticipant.objects.get(
            conversation=conversation,
            user=self.owner,
        )
        participant.draft_text = "do not store this as plaintext"
        with self.assertRaisesMessage(
            ValidationError,
            "Server-side composer drafts are disabled for encrypted conversations.",
        ):
            participant.save(update_fields=["draft_text"])


    def test_legacy_public_join_and_join_request_routes_reject_encrypted_rooms(self):
        conversation = self.make_encrypted_group()
        conversation.is_public = True
        conversation.save(update_fields=["is_public", "updated_at"])

        join = self.client.post(
            f"/api/messenger/groups/{conversation.id}/join/",
            {},
            format="json",
        )
        self.assertEqual(join.status_code, 409, join.data)

        join_requests = self.client.get(
            f"/api/messenger/conversations/{conversation.id}/join-requests/"
        )
        self.assertEqual(join_requests.status_code, 409, join_requests.data)


    def test_standard_dm_creation_never_returns_an_encrypted_dm(self):
        encrypted = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.owner,
            security_mode=Conversation.SecurityMode.MATRIX_E2EE,
            matrix_room_id=f"!secure-dm-{self.owner.pk}-{self.peer.pk}:matrix.example.test",
        )
        ConversationParticipant.objects.create(
            conversation=encrypted,
            user=self.owner,
            role=ConversationParticipant.Role.OWNER,
        )
        ConversationParticipant.objects.create(
            conversation=encrypted,
            user=self.peer,
        )

        response = self.client.post(
            "/api/messenger/conversations/",
            {"type": "private", "user_id": self.peer.id, "security_mode": "standard"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["data"]["security_mode"],
            Conversation.SecurityMode.STANDARD,
        )
        self.assertNotEqual(response.data["data"]["id"], encrypted.id)


    @override_settings(
        MATRIX_HOMESERVER_URL="",
        MATRIX_HOMESERVER_DOMAIN="",
        MATRIX_ADMIN_ACCESS_TOKEN="",
        MATRIX_IDENTITY_ENCRYPTION_KEY="",
    )
    def test_secure_matrix_endpoints_fail_closed_when_not_configured(self):
        device = self.client.post(
            "/api/messenger/secure/device-session/",
            {"device_id": "PD1234567890ABCD"},
            format="json",
        )
        self.assertEqual(device.status_code, 503, device.data)

        identities = self.client.post(
            "/api/messenger/secure/identities/",
            {"user_ids": [self.peer.id]},
            format="json",
        )
        self.assertEqual(identities.status_code, 503, identities.data)

        room = self.client.post(
            "/api/messenger/secure/conversations/",
            {
                "type": "private",
                "member_ids": [self.owner.id, self.peer.id],
                "room_id": "!missing:matrix.example.test",
            },
            format="json",
            HTTP_X_MATRIX_ACCESS_TOKEN="not-a-real-token",
        )
        self.assertEqual(room.status_code, 503, room.data)
        self.assertFalse(Conversation.objects.filter(security_mode=Conversation.SecurityMode.MATRIX_E2EE).exists())

    @override_settings(
        MATRIX_HOMESERVER_URL="https://matrix.example.test",
        MATRIX_HOMESERVER_DOMAIN="matrix.example.test",
        MATRIX_ADMIN_ACCESS_TOKEN="test-admin-token",
        MATRIX_IDENTITY_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    def test_identity_resolution_rejects_non_contact_stranger_before_provisioning(self):
        response = self.client.post(
            "/api/messenger/secure/identities/",
            {"user_ids": [self.peer.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn("contacts or existing Messenger conversation participants", response.data["message"])
        self.assertFalse(MatrixDevice.objects.filter(user=self.peer).exists())

    @override_settings(
        MATRIX_HOMESERVER_URL="https://matrix.example.test",
        MATRIX_HOMESERVER_DOMAIN="matrix.example.test",
        MATRIX_ADMIN_ACCESS_TOKEN="test-admin-token",
        MATRIX_IDENTITY_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
    )
    def test_encrypted_room_mapping_rejects_missing_room_id_before_remote_calls(self):
        Contact.objects.create(owner=self.owner, contact=self.peer)
        response = self.client.post(
            "/api/messenger/secure/conversations/",
            {
                "type": "private",
                "member_ids": [self.owner.id, self.peer.id],
                "room_id": None,
            },
            format="json",
            HTTP_X_MATRIX_ACCESS_TOKEN="fake-token",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("valid Matrix room ID", response.data["message"])
        self.assertFalse(Conversation.objects.filter(security_mode=Conversation.SecurityMode.MATRIX_E2EE).exists())

    def test_matrix_room_binding_cannot_be_remapped_after_registration(self):
        conversation = self.make_encrypted_group()
        conversation.matrix_room_id = f"!replacement-{self.owner.pk}-{self.peer.pk}:matrix.example.test"
        with self.assertRaisesMessage(ValidationError, "security mode and Matrix room bindings are immutable"):
            conversation.save()
        conversation.refresh_from_db()
        self.assertIn("secure-group-", conversation.matrix_room_id)

