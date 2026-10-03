from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from custom_emails.models import EmailLog, EmailTemplate
from custom_emails.serializers import EmailSendSerializer, EmailTemplatePreviewSerializer

User = get_user_model()


class CustomEmailAPIAndSerializerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="email-staff",
            email="staff@example.com",
            password="password123",
            is_staff=True,
        )
        self.admin = User.objects.create_superuser(
            username="email-admin",
            email="admin@example.com",
            password="password123",
        )

    def test_staff_is_not_sufficient_for_email_admin_api(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get("/api/emails/templates/")
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_create_and_list_email_templates(self):
        self.client.force_authenticate(user=self.admin)
        created = self.client.post(
            "/api/emails/templates/",
            {"name": "Welcome", "subject": "Hello {{ user.username }}", "body": "<p>Hi</p>"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)

        listed = self.client.get("/api/emails/templates/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

    def test_email_send_serializer_requires_recipient_or_test_target(self):
        normal = EmailSendSerializer(
            data={"subject": "x", "body": "y"},
        )
        self.assertFalse(normal.is_valid())

        test = EmailSendSerializer(
            data={"is_test": True, "subject": "x", "body": "y"},
        )
        self.assertFalse(test.is_valid())
        self.assertIn("test_email", test.errors)

    def test_email_preview_serializer_rejects_missing_content(self):
        serializer = EmailTemplatePreviewSerializer(data={})
        self.assertFalse(serializer.is_valid())

    def test_failed_email_retry_transitions_back_to_pending(self):
        self.client.force_authenticate(user=self.admin)
        log = EmailLog.objects.create(
            recipient_email="target@example.com",
            subject="Subject",
            body_preview="Body",
            status=EmailLog.Status.FAILED,
        )
        with patch("custom_emails.apis.send_email_log_task.delay") as delay:
            response = self.client.post(f"/api/emails/logs/{log.pk}/retry/")

        self.assertEqual(response.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.PENDING)
        delay.assert_called_once_with(log.pk)
