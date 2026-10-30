from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class LanguagePreferenceAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="language-user",
            email="language@example.com",
            password="test-password-123",
        )
        self.client = APIClient()
        self.url = "/api/users/user/language/"

    def test_language_preference_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_returns_saved_language_and_supported_options(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["language"], "en-us")
        self.assertEqual({item["code"] for item in response.data["languages"]}, {"en-us", "fa"})

    def test_patch_persists_persian_preference(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"language": "fa"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["language"], "fa")
        self.user.refresh_from_db()
        self.assertEqual(self.user.language, "fa")

    def test_unsupported_language_is_rejected_without_mutation(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"language": "de"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "unsupported_language")
        self.user.refresh_from_db()
        self.assertEqual(self.user.language, "en-us")
