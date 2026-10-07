from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from core.throttling import (
    AuthenticationAccountRateThrottle,
    GlobalIPRateThrottle,
    GlobalUserRateThrottle,
    UserScopedRateThrottle,
)


class RateLimitIdentityTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = type("View", (), {})()

    @override_settings(API_GLOBAL_IP_RATE="2/min")
    def test_global_ip_limit_is_shared_by_requests_from_same_ip(self):
        throttle = GlobalIPRateThrottle()
        requests = [
            self.factory.get("/", REMOTE_ADDR="10.10.10.10"),
            self.factory.get("/", REMOTE_ADDR="10.10.10.10"),
            self.factory.get("/", REMOTE_ADDR="10.10.10.10"),
        ]
        self.assertTrue(throttle.allow_request(requests[0], self.view))
        self.assertTrue(throttle.allow_request(requests[1], self.view))
        self.assertFalse(throttle.allow_request(requests[2], self.view))

    @override_settings(API_GLOBAL_USER_RATE="2/min")
    def test_global_user_limit_is_shared_across_ips(self):
        class User:
            is_authenticated = True
            pk = 42

        throttle = GlobalUserRateThrottle()
        first = self.factory.get("/", REMOTE_ADDR="10.10.10.10")
        second = self.factory.get("/", REMOTE_ADDR="10.10.10.11")
        third = self.factory.get("/", REMOTE_ADDR="10.10.10.12")
        for request in (first, second):
            request.user = User()
        third.user = User()

        self.assertTrue(throttle.allow_request(first, self.view))
        self.assertTrue(throttle.allow_request(second, self.view))
        self.assertFalse(throttle.allow_request(third, self.view))

    @override_settings(AUTH_ACCOUNT_RATE="2/min")
    def test_auth_account_limit_follows_identifier_not_ip(self):
        throttle = AuthenticationAccountRateThrottle()
        requests = [
            self.factory.post("/login/", {"email": "User@Example.com"}, format="json", REMOTE_ADDR="10.0.0.1"),
            self.factory.post("/login/", {"email": "user@example.com"}, format="json", REMOTE_ADDR="10.0.0.2"),
            self.factory.post("/login/", {"email": "other@example.com"}, format="json", REMOTE_ADDR="10.0.0.3"),
        ]
        self.assertTrue(throttle.allow_request(requests[0], self.view))
        self.assertTrue(throttle.allow_request(requests[1], self.view))
        self.assertFalse(
            throttle.allow_request(
                self.factory.post("/login/", {"email": "USER@example.com"}, format="json", REMOTE_ADDR="10.0.0.3"),
                self.view,
            )
        )
        self.assertTrue(throttle.allow_request(requests[2], self.view))

    @override_settings(API_SENSITIVE_USER_RATE="1/min")
    def test_user_scoped_limit_is_isolated_by_operation(self):
        class User:
            is_authenticated = True
            pk = 7

        view_a = type("View", (), {"throttle_scope": "operation-a"})()
        view_b = type("View", (), {"throttle_scope": "operation-b"})()
        request = self.factory.post("/")
        request.user = User()

        throttle_a = UserScopedRateThrottle()
        throttle_b = UserScopedRateThrottle()
        self.assertTrue(throttle_a.allow_request(request, view_a))
        self.assertFalse(throttle_a.allow_request(request, view_a))
        self.assertTrue(throttle_b.allow_request(request, view_b))
