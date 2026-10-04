from django.test import TestCase
from rest_framework.permissions import IsAdminUser


class AuthUsersApiImportTests(TestCase):
    def test_invite_api_package_imports_and_resolves_admin_permission(self):
        # Import the public compatibility package exactly as the URL module does.
        from auth_users.api import InviteListAPIView, InviteDeactivateAPIView

        self.assertIs(InviteListAPIView.permission_classes[0], IsAdminUser)
        self.assertIs(InviteDeactivateAPIView.permission_classes[0], IsAdminUser)
