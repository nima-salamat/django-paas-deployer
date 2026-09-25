"""
Tests for ``deployments.common.config``.
"""

import json
import unittest

from deployments.common.config import parse_config, as_bool, as_int, first_present


class TestParseConfig(unittest.TestCase):

    def test_dict_passthrough(self):
        cfg = {"platform": "django", "celery": True}
        result = parse_config(cfg)
        self.assertEqual(result, cfg)
        # Ensure shallow copy
        self.assertIsNot(result, cfg)

    def test_json_string(self):
        cfg = {"platform": "django"}
        result = parse_config(json.dumps(cfg))
        self.assertEqual(result, cfg)

    def test_double_encoded_json(self):
        cfg = {"platform": "django"}
        result = parse_config(json.dumps(json.dumps(cfg)))
        self.assertEqual(result, cfg)

    def test_invalid_json_returns_empty(self):
        self.assertEqual(parse_config("not json"), {})
        self.assertEqual(parse_config(""), {})
        self.assertEqual(parse_config(None), {})

    def test_non_dict_json_returns_empty(self):
        self.assertEqual(parse_config("[1, 2, 3]"), {})
        self.assertEqual(parse_config("\"hello\""), {})
        self.assertEqual(parse_config("42"), {})


class TestAsBool(unittest.TestCase):

    def test_bool_passthrough(self):
        self.assertTrue(as_bool(True))
        self.assertFalse(as_bool(False))

    def test_numeric(self):
        self.assertTrue(as_bool(1))
        self.assertFalse(as_bool(0))
        self.assertTrue(as_bool(2.5))

    def test_string(self):
        for true_val in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
            self.assertTrue(as_bool(true_val), f"{true_val!r} should be True")
        for false_val in ("0", "false", "no", "off", ""):
            self.assertFalse(as_bool(false_val), f"{false_val!r} should be False")

    def test_fallback(self):
        self.assertFalse(as_bool(None))


class TestAsInt(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(as_int("42", default=0), 42)
        self.assertEqual(as_int(42, default=0), 42)
        self.assertEqual(as_int(42.9, default=0), 42)

    def test_invalid_falls_back(self):
        self.assertEqual(as_int("abc", default=7), 7)
        self.assertEqual(as_int(None, default=7), 7)

    def test_bounds(self):
        self.assertEqual(as_int(0, default=1, minimum=1), 1)
        self.assertEqual(as_int(1000, default=1, maximum=100), 100)


class TestFirstPresent(unittest.TestCase):

    def test_returns_first_non_empty(self):
        self.assertEqual(first_present("", None, "first", "second"), "first")
        self.assertEqual(first_present("a", "b"), "a")

    def test_all_empty(self):
        self.assertIsNone(first_present("", None, ""))

    def test_custom_skip(self):
        self.assertEqual(first_present("skip", "real", skip=("skip",)), "real")


if __name__ == "__main__":
    unittest.main()
