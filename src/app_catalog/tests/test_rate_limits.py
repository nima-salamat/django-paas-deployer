from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import User
from app_catalog.apis import CatalogPermissionMixin


@override_settings(
    API_GLOBAL_IP_RATE="1000/min",
    API_GLOBAL_USER_RATE="1000/min",
)
class ReadyAppRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="ready-rate-user",
            email="ready-rate@example.test",
            password="password123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_catalog_resolve_is_throttled_as_a_mutation(self):
        original_rate = CatalogPermissionMixin.throttle_user_rate
        CatalogPermissionMixin.throttle_user_rate = "2/min"
        self.addCleanup(setattr, CatalogPermissionMixin, "throttle_user_rate", original_rate)
        url = "/api/application-catalog/apps/does-not-exist/resolve/"
        first = self.client.post(url, {}, format="json")
        second = self.client.post(url, {}, format="json")
        third = self.client.post(url, {}, format="json")

        self.assertEqual(first.status_code, 404)
        self.assertEqual(second.status_code, 404)
        self.assertEqual(third.status_code, 429)
