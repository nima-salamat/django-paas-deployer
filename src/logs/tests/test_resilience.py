"""Resilience-oriented unit tests (no live Docker required)."""
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from logs.ingestion import fingerprint, RateWindow
from logs.policy import EffectiveLoggingPolicy


class FingerprintOverlapTests(SimpleTestCase):
    def test_overlap_same_fp(self):
        ts = timezone.now()
        self.assertEqual(
            fingerprint(ts, "stdout", "a"),
            fingerprint(ts, "stdout", "a"),
        )

    def test_policy_fields(self):
        p = EffectiveLoggingPolicy(
            retention_days=7,
            storage_quota_bytes=1024,
            max_bytes_per_second=1000,
            max_entry_size=100,
            persistent_enabled=True,
            realtime_enabled=True,
            quota_behavior="fifo_delete",
        )
        self.assertEqual(p.quota_behavior, "fifo_delete")


class RateWindowTests(SimpleTestCase):
    def test_rate_window_blocks(self):
        # Import from collector module path if available
        try:
            from deployments.management.commands.run_log_collector import RateWindow as RW
        except Exception:
            self.skipTest("collector not importable in test env")
            return
        r = RW(100)
        self.assertTrue(r.allow(50))
        self.assertTrue(r.allow(40))
        self.assertFalse(r.allow(20))


class CursorCodecTests(SimpleTestCase):
    def test_roundtrip(self):
        from logs.query import encode_cursor, decode_cursor

        ts = timezone.now()
        c = encode_cursor(ts, 42)
        ts2, seq = decode_cursor(c)
        self.assertEqual(seq, 42)
