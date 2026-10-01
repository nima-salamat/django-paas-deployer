from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.application import ensure_service_access
from agent.errors import AgentError


class AgentAuthorizationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="test")
        self.shared = User.objects.create_user(username="shared", email="shared@example.com", password="test")
        self.service = Mock()
        self.service.user_id = self.owner.pk
        self.service.pk = "service-1"

    def test_own_service_does_not_need_share(self):
        with patch("services.api.sharing.user_can_access_service") as checker:
            self.assertIsNone(ensure_service_access(self.service, self.owner, action="can_view"))
            checker.assert_not_called()

    @patch("services.api.sharing.user_can_access_service", return_value=(True, Mock()))
    def test_shared_service_uses_existing_share_boundary(self, checker):
        ensure_service_access(self.service, self.shared, action="can_shell")
        checker.assert_called_once_with(self.service, self.shared, action="can_shell")

    @patch("services.api.sharing.user_can_access_service", return_value=(False, None))
    def test_shared_service_denied_by_existing_share_boundary(self, checker):
        with self.assertRaises(AgentError) as ctx:
            ensure_service_access(self.service, self.shared, action="can_shell")
        self.assertEqual(ctx.exception.code, "PERMISSION_DENIED")
        checker.assert_called_once_with(self.service, self.shared, action="can_shell")
