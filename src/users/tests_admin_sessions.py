from django.test import TestCase
from rest_framework.test import APIClient
from auth_users.models import LoginSettings, UserSession
from auth_users.services import issue_tokens_for_user
from users.models import Rule, User


class AdminUserSessionAPITests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="session-operator",
            email="session-operator@example.test",
            password="pass12345",
        )
        self.operator.is_staff = True
        self.operator.save(update_fields=["is_staff"])
        Rule.objects.create(user=self.operator, rules=[])

        self.target = User.objects.create_user(
            username="session-target",
            email="session-target@example.test",
            password="pass12345",
        )
        LoginSettings.objects.create(max_active_sessions=5)

    def _client(self):
        tokens = issue_tokens_for_user(self.operator)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return client

    def _target_session(self):
        return issue_tokens_for_user(self.target)["session_id"]

    def test_permission_catalog_exposes_session_permissions(self):
        self.operator.rule.rules = ["users.view"]
        self.operator.rule.save(update_fields=["rules"])

        response = self._client().get("/api/users/admin/permissions/")

        self.assertEqual(response.status_code, 200)
        permissions = response.data["data"]["permissions"]
        self.assertIn("auth_sessions.view", permissions)
        self.assertIn("auth_sessions.manage", permissions)

    def test_session_list_requires_view_permission(self):
        self.operator.rule.rules = ["users.view"]
        self.operator.rule.save(update_fields=["rules"])

        response = self._client().get(
            f"/api/users/admin/users/{self.target.id}/sessions/"
        )

        self.assertEqual(response.status_code, 403)

    def test_session_list_is_allowed_with_view_permission(self):
        self.operator.rule.rules = ["auth_sessions.view"]
        self.operator.rule.save(update_fields=["rules"])
        session_id = self._target_session()

        response = self._client().get(
            f"/api/users/admin/users/{self.target.id}/sessions/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["active_count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["id"], session_id)

    def test_revoke_requires_manage_permission(self):
        self.operator.rule.rules = ["auth_sessions.view"]
        self.operator.rule.save(update_fields=["rules"])
        session_id = self._target_session()

        response = self._client().delete(
            f"/api/users/admin/users/{self.target.id}/sessions/{session_id}/"
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            UserSession.objects.filter(
                session_id=session_id,
                revoked_at__isnull=True,
            ).exists()
        )

    def test_manage_permission_can_revoke_one_session(self):
        self.operator.rule.rules = ["auth_sessions.view", "auth_sessions.manage"]
        self.operator.rule.save(update_fields=["rules"])
        session_id = self._target_session()

        response = self._client().delete(
            f"/api/users/admin/users/{self.target.id}/sessions/{session_id}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            UserSession.objects.filter(
                session_id=session_id,
                revoked_at__isnull=True,
            ).exists()
        )

    def test_manage_permission_can_revoke_all_sessions(self):
        self.operator.rule.rules = ["auth_sessions.view", "auth_sessions.manage"]
        self.operator.rule.save(update_fields=["rules"])
        first = self._target_session()
        second = self._target_session()

        response = self._client().post(
            f"/api/users/admin/users/{self.target.id}/sessions/logout-all/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["revoked"], 2)
        self.assertEqual(
            UserSession.objects.filter(
                user=self.target,
                revoked_at__isnull=True,
            ).count(),
            0,
        )
        self.assertNotEqual(first, second)
