from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from core import app_cache


class CacheKeyContractTests(SimpleTestCase):
    def test_query_keys_are_stable_and_parameter_order_independent(self):
        left = app_cache.make_query_key("svc:user", 7, {"page": 2, "q": "hello"})
        right = app_cache.make_query_key("svc:user", 7, {"q": "hello", "page": 2})
        self.assertEqual(left, right)

    def test_query_keys_are_isolated_by_user_and_namespace(self):
        self.assertNotEqual(
            app_cache.service_user_list_key(1, {"page": 1}),
            app_cache.service_user_list_key(2, {"page": 1}),
        )
        self.assertNotEqual(
            app_cache.plan_list_key({"page": 1}),
            app_cache.plan_admin_list_key({"page": 1}),
        )

    def test_empty_parameters_do_not_change_query_identity(self):
        self.assertEqual(
            app_cache.make_query_key("x", 1, {}),
            app_cache.make_query_key("x", 1, {"unused": ""}),
        )

    def test_ttl_is_bounded_and_defaults_when_setting_lookup_fails(self):
        with patch("core.settings_service.get_int", return_value=999999999):
            self.assertEqual(
                app_cache.get_cache_ttl("plan"),
                7 * 24 * 3600,
            )
        with patch("core.settings_service.get_int", side_effect=RuntimeError("boom")):
            self.assertEqual(app_cache.get_cache_ttl("plan"), app_cache.PLAN_TTL)


class CacheSerializationTests(SimpleTestCase):
    def test_json_round_trip_supports_django_json_values(self):
        value = {
            "amount": Decimal("12.50"),
            "created": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        }
        encoded = app_cache._dumps(value)
        decoded = app_cache._loads(encoded)
        self.assertEqual(decoded["amount"], 12.5)
        self.assertEqual(decoded["created"], "2026-01-02T03:04:05Z")

    def test_loads_handles_bytes_and_malformed_payloads(self):
        self.assertEqual(app_cache._loads(b'{"ok":true}'), {"ok": True})
        self.assertIsNone(app_cache._loads(b"not-json"))
        self.assertIsNone(app_cache._loads(object()))


class CacheFailurePolicyTests(SimpleTestCase):
    def test_cache_operations_soft_fail_when_redis_is_unavailable(self):
        with patch("core.app_cache._redis", return_value=None):
            self.assertIsNone(app_cache.cache_get("k"))
            self.assertFalse(app_cache.cache_set("k", {"v": 1}, 60))
            self.assertEqual(app_cache.delete_cache_keys("k"), 0)
            self.assertEqual(app_cache.cache_delete_pattern("x:*"), 0)
            self.assertEqual(app_cache.scan_app_cache_keys("x:"), [])
            self.assertEqual(
                app_cache.get_app_cache_overview(),
                {"redis_ok": False, "svc": 0, "plan": 0, "tkt": 0, "usr": 0, "msgcache": 0, "memory": {}},
            )

    def test_cache_set_uses_setex_for_positive_ttl(self):
        redis = Mock()
        with patch("core.app_cache._redis", return_value=redis):
            self.assertTrue(app_cache.cache_set("k", {"v": 1}, 60))
        redis.setex.assert_called_once()

    def test_cache_set_without_expiry_uses_set(self):
        redis = Mock()
        with patch("core.app_cache._redis", return_value=redis):
            self.assertTrue(app_cache.cache_set("k", {"v": 1}, 0))
        redis.set.assert_called_once()

    def test_cache_get_returns_none_when_redis_read_fails(self):
        redis = Mock()
        redis.get.side_effect = RuntimeError("redis down")
        with patch("core.app_cache._redis", return_value=redis):
            self.assertIsNone(app_cache.cache_get("k"))

    def test_cache_set_returns_false_when_redis_write_fails(self):
        redis = Mock()
        redis.setex.side_effect = RuntimeError("redis down")
        with patch("core.app_cache._redis", return_value=redis):
            self.assertFalse(app_cache.cache_set("k", {"v": 1}, 60))
