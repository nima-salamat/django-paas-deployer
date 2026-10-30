from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.http import HttpResponse
from django.test import RequestFactory
from types import SimpleNamespace
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


class UserLanguageMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_saved_user_language_becomes_accept_language_fallback(self):
        from core.middleware import UserLanguageMiddleware

        request = self.factory.get("/api/users/user/")
        request.user = SimpleNamespace(is_authenticated=True, language="fa")
        response = UserLanguageMiddleware(
            lambda current: HttpResponse(current.headers.get("Accept-Language", ""))
        )(request)
        self.assertEqual(request.headers.get("Accept-Language"), "fa")
        self.assertEqual(response.content, b"fa")

    def test_explicit_accept_language_header_takes_precedence(self):
        from core.middleware import UserLanguageMiddleware

        request = self.factory.get("/api/users/user/", HTTP_ACCEPT_LANGUAGE="en-US")
        request.user = SimpleNamespace(is_authenticated=True, language="fa")
        UserLanguageMiddleware(lambda current: HttpResponse("ok"))(request)
        self.assertEqual(request.headers.get("Accept-Language"), "en-US")

    def test_anonymous_request_does_not_receive_user_language(self):
        from core.middleware import UserLanguageMiddleware

        request = self.factory.get("/api/users/user/")
        request.user = SimpleNamespace(is_authenticated=False, language="fa")
        UserLanguageMiddleware(lambda current: HttpResponse("ok"))(request)
        self.assertIsNone(request.headers.get("Accept-Language"))
