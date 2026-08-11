from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Conversation, ConversationParticipant, Message, MessageAttachment


@override_settings(MEDIA_ROOT="test_media")
class MessengerMediaTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.sender = User.objects.create_user(username="sender", email="s@example.com", password="pass")
        self.receiver = User.objects.create_user(username="receiver", email="r@example.com", password="pass")
        self.conv = Conversation.objects.create(type=Conversation.Type.PRIVATE)
        ConversationParticipant.objects.create(conversation=self.conv, user=self.sender)
        ConversationParticipant.objects.create(conversation=self.conv, user=self.receiver)
        self.client.force_authenticate(self.sender)

    def test_invalid_attachment_does_not_create_empty_message(self):
        upload = SimpleUploadedFile("bad.exe", b"MZnot-allowed", content_type="application/octet-stream")

        res = self.client.post(
            f"/api/messenger/conversations/{self.conv.id}/messages/",
            {"body": "", "files": [upload]},
            format="multipart",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(MessageAttachment.objects.count(), 0)

    def test_voice_upload_creates_voice_attachment(self):
        upload = SimpleUploadedFile("voice_123.webm", b"\x1a\x45\xdf\xa3audio", content_type="audio/webm")

        res = self.client.post(
            f"/api/messenger/conversations/{self.conv.id}/messages/",
            {"body": "", "files": [upload]},
            format="multipart",
        )

        self.assertEqual(res.status_code, 201)
        att = MessageAttachment.objects.get()
        self.assertEqual(att.kind, "voice")
        self.assertEqual(att.content_type, "audio/webm")

    def test_media_download_is_inline_with_content_type(self):
        msg = Message.objects.create(conversation=self.conv, sender=self.sender)
        att = MessageAttachment.objects.create(
            conversation=self.conv,
            message=msg,
            uploaded_by=self.sender,
            file=SimpleUploadedFile("song.mp3", b"ID3audio", content_type="audio/mpeg"),
            original_filename="song.mp3",
            content_type="audio/mpeg",
            size=8,
            kind="audio",
        )

        res = self.client.get(f"/api/messenger/attachments/{att.id}/download/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "audio/mpeg")
        self.assertIn("inline", res["Content-Disposition"])
