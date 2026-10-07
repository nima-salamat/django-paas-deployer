from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import User
from auth_users.models import LoginSettings


@override_settings(
    AUTH_ACCOUNT_RATE="2/min",
    AUTH_IP_RATE="100/min",
    API_GLOBAL_IP_RATE="1000/min",
    API_GLOBAL_USER_RATE="1000/min",
)
class AuthenticationRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        LoginSettings.objects.create(
            require_otp=True,
            require_password=False,
            password_as_second_factor=False,
        )
        self.user = User.objects.create_user(
            username="rate-user",
            email="rate@example.test",
            password="password123",
        )

    @patch("auth_users.api.auth_flow.send_otp", return_value="12345678")
    def test_login_is_limited_per_account_even_when_ip_changes(self, send_otp):
        first_client = APIClient()
        second_client = APIClient()
        payload = {"email": self.user.email}

        first = first_client.post(
            "/auth/api/authentication/",
            payload,
            format="json",
            REMOTE_ADDR="10.0.0.1",
        )
        second = first_client.post(
            "/auth/api/authentication/",
            payload,
            format="json",
            REMOTE_ADDR="10.0.0.1",
        )
        blocked_from_other_ip = second_client.post(
            "/auth/api/authentication/",
            payload,
            format="json",
            REMOTE_ADDR="10.0.0.2",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked_from_other_ip.status_code, 429)
        self.assertEqual(send_otp.call_count, 2)

    @override_settings(AUTH_ACCOUNT_RATE="100/min", AUTH_IP_RATE="2/min")
    @patch("auth_users.api.auth_flow.send_otp", return_value="12345678")
    def test_login_ip_limit_blocks_identifier_rotation(self, send_otp):
        client = APIClient()
        users = [
            User.objects.create_user(
                username=f"rotation-{index}",
                email=f"rotation-{index}@example.test",
                password="password123",
            )
            for index in range(2)
        ]

        first = client.post(
            "/auth/api/authentication/",
            {"email": users[0].email},
            format="json",
            REMOTE_ADDR="10.0.0.9",
        )
        second = client.post(
            "/auth/api/authentication/",
            {"email": users[1].email},
            format="json",
            REMOTE_ADDR="10.0.0.9",
        )
        blocked = client.post(
            "/auth/api/authentication/",
            {"email": "unknown@example.test"},
            format="json",
            REMOTE_ADDR="10.0.0.9",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(send_otp.call_count, 2)

    @patch("auth_users.api.auth_flow.send_otp", return_value="12345678")
    def test_login_legacy_alias_inherits_the_same_account_limit(self, send_otp):
        client = APIClient()
        payload = {"email": self.user.email}

        first = client.post("/auth/api/login/", payload, format="json")
        second = client.post("/auth/api/login/", payload, format="json")
        blocked = client.post("/auth/api/login/", payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(send_otp.call_count, 2)
