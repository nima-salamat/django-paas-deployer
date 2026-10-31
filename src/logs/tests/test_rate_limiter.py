from django.test import SimpleTestCase

from logs.ingest_api import _PerServiceRateLimiter


class RuntimeLogRateLimiterTests(SimpleTestCase):
    def test_process_fallback_enforces_byte_window(self):
        limiter = _PerServiceRateLimiter()
        accepted, dropped, dropped_bytes = limiter._filter_local(
            "service-test",
            [
                {"message": "a" * 800},
                {"message": "b" * 800},
            ],
            1024,
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(dropped, 1)
        self.assertEqual(dropped_bytes, 800)
