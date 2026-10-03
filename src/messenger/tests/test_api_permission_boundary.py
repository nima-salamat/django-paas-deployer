from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class MessengerAPIPermissionBoundaryTests(TestCase):
    def test_messenger_endpoints_require_authentication(self):
        client = APIClient()
        response = client.get("/api/messenger/users/by-username/?username=missing")
        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_user_can_access_user_lookup(self):
        user = User.objects.create_user(
            username="messenger-auth",
            email="messenger@example.com",
            password="password123",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/messenger/users/by-username/?username=messenger-auth")
        self.assertEqual(response.status_code, 200)
