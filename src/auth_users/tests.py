from django.test import TestCase
from rest_framework.permissions import IsAdminUser


class AuthUsersApiImportTests(TestCase):
    def test_invite_api_package_imports_and_resolves_admin_permission(self):
        # Import the public compatibility package exactly as the URL module does.
        from auth_users.api import InviteListAPIView, InviteDeactivateAPIView

        self.assertIs(InviteListAPIView.permission_classes[0], IsAdminUser)
        self.assertIs(InviteDeactivateAPIView.permission_classes[0], IsAdminUser)


class ExistingAccountReauthenticationTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()

    def test_reauthentication_never_creates_an_account_when_identifier_is_not_found(self):
        from unittest.mock import patch
        from django.contrib.auth import get_user_model

        User = get_user_model()
        before = User.objects.count()
        with patch("auth_users.api.auth_flow.can_create_user") as can_create:
            response = self.client.post(
                "/auth/api/authentication/",
                {
                    "email": "not-an-existing-account@example.invalid",
                    "existing_account_only": True,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 401, response.data)
        self.assertFalse(response.data.get("success", True))
        self.assertEqual(User.objects.count(), before)
        can_create.assert_not_called()

    def test_reauthentication_uses_the_current_backend_otp_and_password_policy(self):
        from unittest.mock import patch
        from django.contrib.auth import get_user_model
        from auth_users.models import AuthCode, LoginSettings

        User = get_user_model()
        user = User.objects.create_user(
            username="reauth-existing-user",
            email="reauth-existing-user@example.invalid",
            password="StrongPass123!",
        )
        settings = LoginSettings.get_solo()
        settings.allow_login = True
        settings.allow_email = True
        settings.allow_phone = True
        settings.require_otp = True
        settings.require_password = True
        settings.password_as_second_factor = True
        settings.save()

        with patch("auth_users.api.auth_flow.send_otp") as send_otp:
            response = self.client.post(
                "/auth/api/authentication/",
                {
                    "email": user.email,
                    "existing_account_only": True,
                    "device_id": "PDREAUTH1234",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["created"])
        self.assertEqual(response.data["next_step"], "otp")
        self.assertTrue(response.data["requires_otp"])
        self.assertTrue(response.data["requires_password"])
        send_otp.assert_called_once_with(
            user=user,
            contact=user.email,
            channel="email",
            purpose=AuthCode.PURPOSE_LOGIN,
        )
