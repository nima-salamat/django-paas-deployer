from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from .models import Conversation, ConversationParticipant, Message


User = get_user_model()


class MessengerReadStateTests(APITestCase):
    def setUp(self):
        self.reader = User.objects.create_user(username="reader", password="pass12345")
        self.sender = User.objects.create_user(username="sender", password="pass12345")
        self.conversation = Conversation.objects.create(
            type=Conversation.Type.PRIVATE,
            created_by=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.reader,
            role=ConversationParticipant.Role.MEMBER,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.sender,
            role=ConversationParticipant.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.reader)

    def test_mark_read_advances_cursor_and_invalidates_reader_list_projection(self):
        first = Message.objects.create(
            conversation=self.conversation,
            sender=self.sender,
            body="first",
        )
        second = Message.objects.create(
            conversation=self.conversation,
            sender=self.sender,
            body="second",
        )

        with patch(
            "messenger.message_cache.ConversationCacheService.invalidate_user_conv_list"
        ) as invalidate:
            response = self.client.post(
                f"/api/messenger/conversations/{self.conversation.id}/read/",
                {"message_ids": [first.id, second.id]},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["receipts"], 2)
        participant = ConversationParticipant.objects.get(
            conversation=self.conversation,
            user=self.reader,
        )
        self.assertEqual(participant.last_read_at, second.created_at)
        invalidate.assert_called_once_with(self.reader.id)

    def test_mark_read_does_not_move_cursor_backward(self):
        first = Message.objects.create(
            conversation=self.conversation,
            sender=self.sender,
            body="first",
        )
        second = Message.objects.create(
            conversation=self.conversation,
            sender=self.sender,
            body="second",
        )

        self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/read/",
            {"message_ids": [second.id]},
            format="json",
        )
        before = ConversationParticipant.objects.get(
            conversation=self.conversation,
            user=self.reader,
        ).last_read_at

        response = self.client.post(
            f"/api/messenger/conversations/{self.conversation.id}/read/",
            {"message_ids": [first.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        after = ConversationParticipant.objects.get(
            conversation=self.conversation,
            user=self.reader,
        ).last_read_at
        self.assertEqual(after, before)
