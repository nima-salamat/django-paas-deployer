from django.core.cache import cache
from django.test import SimpleTestCase

from core.throttling import check_scope, remaining, ScopedRateThrottle, user_scope


class ScopedThrottlingUnitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_window_limit(self):
        for _ in range(5):
            self.assertTrue(check_scope("unit:x", 5, 30))
        self.assertFalse(check_scope("unit:x", 5, 30))

    def test_zero_limit_means_unlimited(self):
        self.assertTrue(check_scope("unit:z", 0, 30))
        self.assertTrue(check_scope("unit:z", -1, 30))

    def test_remaining_counts_down(self):
        check_scope("unit:r", 3, 60)
        self.assertEqual(remaining("unit:r", 3), 2)

    def test_parse_rate_variants(self):
        self.assertEqual(ScopedRateThrottle.parse_rate("12/min"), (12, 60))
        self.assertEqual(ScopedRateThrottle.parse_rate("1/second"), (1, 1))
        self.assertEqual(ScopedRateThrottle.parse_rate("7/h"), (7, 3600))

    def test_user_scope_builder(self):
        class R:
            user = type("U", (), {"pk": 42})()
        builder = user_scope("deploy:create")
        self.assertEqual(builder(R()), "deploy:create:user:42")
