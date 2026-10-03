from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class LoggingHealthAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="log-health-staff",
            email="logs@example.com",
            password="password123",
            is_staff=True,
        )

    def test_logging_health_requires_staff_authentication(self):
        anonymous = self.client.get("/services/admin/logging/health/")
        self.assertIn(anonymous.status_code, (401, 403))

        self.client.force_authenticate(user=self.staff)
        response = self.client.get("/services/admin/logging/health/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("overall_status", payload)
        self.assertNotIn("message", payload)
