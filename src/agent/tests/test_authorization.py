from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.application import ensure_service_access
from agent.errors import AgentError


class AgentAuthorizationTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(username="owner_user",email="owner_user@example.com",password="example-password")
        self.other=User.objects.create_user(username="other_user",email="other_user@example.com",password="example-password")
        self.service=Mock()
        self.service.user_id=self.owner.pk

    def test_owner_does_not_use_share_checker(self):
        with patch("services.api.sharing.user_can_access_service") as checker:
            self.assertIsNone(ensure_service_access(self.service,self.owner,action="can_view"))
            checker.assert_not_called()

    @patch("services.api.sharing.user_can_access_service",return_value=(True,Mock()))
    def test_share_action_is_delegated(self,checker):
        ensure_service_access(self.service,self.other,action="can_shell")
        checker.assert_called_once_with(self.service,self.other,action="can_shell")

    @patch("services.api.sharing.user_can_access_service",return_value=(False,None))
    def test_share_denial_is_preserved(self,checker):
        with self.assertRaises(AgentError) as ctx:
            ensure_service_access(self.service,self.other,action="can_shell")
        self.assertEqual(ctx.exception.code,"PERMISSION_DENIED")
        checker.assert_called_once_with(self.service,self.other,action="can_shell")
