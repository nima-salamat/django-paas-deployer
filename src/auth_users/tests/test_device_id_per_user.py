import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from auth_users.models import Device, LoginSettings, UserSession
from users.models import User


class DeviceIdentityAcrossAccountsLoginTests(TestCase):
    device_id = "12345678-1234-5678-1234-567812345678"
    password = "SafePass12345!"

    def setUp(self):
        cache.clear()
        LoginSettings.objects.create(
            require_otp=False,
            require_password=True,
            password_as_second_factor=False,
        )
        self.users = [
            User.objects.create_user(
                username="device-account-one",
                email="device-account-one@example.test",
                password=self.password,
            ),
            User.objects.create_user(
                username="device-account-two",
                email="device-account-two@example.test",
                password=self.password,
            ),
        ]
        self.client = APIClient()

    def _login(self, user):
        return self.client.post(
            "/auth/api/login/token/",
            {
                "email": user.email,
                "password": self.password,
                "device_id": self.device_id,
            },
            format="json",
        )

    def test_same_browser_device_id_can_log_in_to_multiple_accounts(self):
        responses = [
            self._login(self.users[0]),
            self._login(self.users[1]),
            self._login(self.users[0]),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.data["success"])
            self.assertIn("access", response.data)
            self.assertIn("refresh", response.data)

        public_id = uuid.UUID(self.device_id)
        self.assertEqual(Device.objects.filter(public_id=public_id).count(), 2)
        for user in self.users:
            self.assertEqual(
                Device.objects.filter(user=user, public_id=public_id).count(),
                1,
            )
            self.assertEqual(
                UserSession.objects.filter(user=user, device__public_id=public_id).count(),
                2 if user == self.users[0] else 1,
            )
