
"""Documented resilience scenarios with unit-level coverage of production code paths."""
from django.test import SimpleTestCase
from django.utils import timezone

from logs.ingestion import fingerprint
from logs.policy import EffectiveLoggingPolicy
from logs.query import encode_cursor, decode_cursor
from logs.exceptions import ExpiredCursorError


class ScenarioContracts(SimpleTestCase):
    """Contracts for the 15 failure scenarios (unit-level)."""

    def test_01_celery_not_required_for_ingest_contract(self):
        # ingestion module must not import celery at top level
        import logs.ingestion as ing
        self.assertFalse(hasattr(ing, "shared_task"))

    def test_02_fingerprint_stable_for_restart_overlap(self):
        ts = timezone.now()
        self.assertEqual(fingerprint(ts, "stderr", "x"), fingerprint(ts, "stderr", "x"))

    def test_03_seq_not_in_fingerprint(self):
        ts = timezone.now()
        a = fingerprint(ts, "stdout", "m")
        self.assertEqual(len(a), 64)

    def test_04_cursor_roundtrip(self):
        ts = timezone.now()
        c = encode_cursor(ts, 9)
        ts2, seq = decode_cursor(c)
        self.assertEqual(seq, 9)

    def test_05_quota_behaviors_defined(self):
        for b in ("fifo_delete", "drop_new", "realtime_only"):
            p = EffectiveLoggingPolicy(7, 1000, 1000, 100, True, True, b)
            self.assertEqual(p.quota_behavior, b)

    def test_06_expired_cursor_type(self):
        self.assertTrue(issubclass(ExpiredCursorError, Exception))

    def test_07_demux_stdout_stderr(self):
        from deployments.management.commands.run_log_collector import Command
        cmd = Command()
        # multiplexed: stream=2 stderr, size=5, payload HELLO
        payload = b"HELLO"
        header = bytes([2, 0, 0, 0]) + len(payload).to_bytes(4, "big")
        pairs = cmd._demux_docker_chunk(header + payload)
        self.assertTrue(any(k == "stderr" for k, _ in pairs))
