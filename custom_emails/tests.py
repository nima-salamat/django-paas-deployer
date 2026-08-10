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
        self.tpl = EmailTemplate.objects.create(name="Welcome", subject="Hi {{ user.username }}", body="<p>Hello {{ user.email }}</p>")

    def test_template_create(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/emails/templates/", {"name":"T2","subject":"S","body":"<p>B</p>"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_render(self):
        ctx = build_context(self.admin)
        out = render_template_string("Hello {{ user.username }}", ctx)
        self.assertIn(self.admin.username, out)

    def test_permission(self):
        user = User.objects.create_user(username="u", email="u@test.com", password="pass12345")
        self.client.force_authenticate(user)
        resp = self.client.get("/api/emails/templates/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
