from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import EmailTemplate, EmailLog
from .services import render_template_string, build_context

User = get_user_model()

class EmailAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin1", email="a@test.com", password="pass12345", is_staff=True, is_superuser=True)
        self.staff = User.objects.create_user(username="staff1", email="s@test.com", password="pass12345", is_staff=True)
        self.user = User.objects.create_user(username="u1", email="u1@test.com", password="pass12345")
        self.tpl = EmailTemplate.objects.create(name="Welcome", subject="Hi {{ user.username }}", body="<p>Hello {{ user.email }}</p>")

    def test_user_cannot_access_templates(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/emails/templates/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_access_templates(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/api/emails/templates/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_templates(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/emails/templates/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_render(self):
        ctx = build_context(self.admin)
        out = render_template_string("Hello {{ user.username }}", ctx)
        self.assertIn(self.admin.username, out)

    def test_retry_failed(self):
        log = EmailLog.objects.create(
            recipient_email="x@test.com", subject="S", body_preview="B",
            status=EmailLog.Status.FAILED, error_message="boom", sent_by=self.admin,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/emails/logs/{log.id}/retry/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.PENDING)
