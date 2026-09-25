"""Regression coverage for runtime stream modes and recovery semantics."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from logs.policy import EffectiveLoggingPolicy


class StreamModeTests(SimpleTestCase):
    def policy(self, *, persistent=True, realtime=True, behavior="fifo_delete"):
        return EffectiveLoggingPolicy(
            retention_days=7,
            storage_quota_bytes=1024 * 1024,
            max_bytes_per_second=100_000,
            max_entry_size=16_384,
            persistent_enabled=persistent,
            realtime_enabled=realtime,
            quota_behavior=behavior,
        )

    def test_effective_modes(self):
        self.assertEqual(self.policy().mode, "persistent_realtime")
        self.assertEqual(self.policy(realtime=False).mode, "persistent_only")
        self.assertEqual(self.policy(persistent=False).mode, "realtime_only")
        self.assertEqual(self.policy(persistent=False, realtime=False).mode, "disabled")
        self.assertEqual(
            self.policy(behavior="realtime_only").mode,
            "realtime_only",
        )

    @patch("logs.realtime.publish_log_events")
    @patch("logs.ingestion.ingest_lines")
    def test_realtime_only_publishes_ephemeral(self, mock_ingest, mock_publish):
        from deployments.management.commands.run_log_collector import Command

        mock_ingest.return_value = {
            "inserted": 0,
            "duplicates": 0,
            "dropped": 0,
            "bytes": 0,
            "persisted": False,
            "realtime_only": True,
            "inserted_entries": [],
        }
        cmd = Command()
        cmd._buffer = MagicMock()
        service = SimpleNamespace(pk="service-1")
        stream = SimpleNamespace(pk=10)
        lines = [{"ts": timezone.now(), "stream": "stderr", "message": "live"}]

        cmd._persist_batch("collector-1", service, stream, self.policy(persistent=False), lines)

        mock_publish.assert_called_once()
        event = mock_publish.call_args.args[1][0]
        self.assertFalse(event["persisted"])
        self.assertTrue(event["ephemeral"])
        self.assertEqual(event["stream"], "stderr")
        self.assertIsNone(event["cursor"])

    @patch("logs.realtime.publish_log_events")
    @patch("logs.ingestion.ingest_lines")
    def test_drop_new_preserves_realtime_delivery(self, mock_ingest, mock_publish):
        from deployments.management.commands.run_log_collector import Command

        mock_ingest.return_value = {
            "inserted": 0,
            "duplicates": 0,
            "dropped": 2,
            "bytes": 0,
            "persisted": True,
            "inserted_entries": [],
        }
        cmd = Command()
        cmd._buffer = MagicMock()
        service = SimpleNamespace(pk="service-1")
        stream = SimpleNamespace(pk=10)
        lines = [
            {"ts": timezone.now(), "stream": "stdout", "message": "a"},
            {"ts": timezone.now(), "stream": "stderr", "message": "b"},
        ]

        cmd._persist_batch(
            "collector-1",
            service,
            stream,
            self.policy(behavior="drop_new"),
            lines,
        )

        mock_publish.assert_called_once()
        events = mock_publish.call_args.args[1]
        self.assertEqual([e["stream"] for e in events], ["stdout", "stderr"])
        self.assertTrue(all(not e["persisted"] for e in events))

    @patch("logs.realtime.publish_log_events")
    @patch("logs.ingestion.ingest_lines")
    def test_publish_uses_exact_inserted_rows(self, mock_ingest, mock_publish):
        from deployments.management.commands.run_log_collector import Command

        ts = timezone.now()
        mock_ingest.return_value = {
            "inserted": 1,
            "duplicates": 1,
            "dropped": 0,
            "bytes": 14,
            "persisted": True,
            "inserted_entries": [{
                "id": 55,
                "stream_id": 10,
                "ts": ts,
                "seq": 7,
                "stream": "stderr",
                "level": "error",
                "message": "actual inserted",
                "byte_size": 14,
                "truncated": False,
            }],
        }
        cmd = Command()
        cmd._buffer = MagicMock()
        service = SimpleNamespace(pk="service-1")
        stream = SimpleNamespace(pk=10)
        lines = [
            {"ts": ts, "stream": "stdout", "message": "duplicate"},
            {"ts": ts, "stream": "stderr", "message": "actual inserted"},
        ]

        with patch("logs.query.encode_cursor", return_value="cursor"):
            cmd._persist_batch(
                "collector-1",
                service,
                stream,
                self.policy(),
                lines,
            )

        event = mock_publish.call_args.args[1][0]
        self.assertEqual(event["id"], 55)
        self.assertEqual(event["seq"], 7)
        self.assertEqual(event["stream"], "stderr")
        self.assertTrue(event["persisted"])

    def test_cursor_with_entry_id_roundtrip(self):
        from logs.query import _decode_cursor_parts, decode_cursor, encode_cursor

        ts = timezone.now()
        cursor = encode_cursor(ts, 3, entry_id=99)
        ts2, seq2, entry_id = _decode_cursor_parts(cursor)
        self.assertEqual(ts2, ts)
        self.assertEqual(seq2, 3)
        self.assertEqual(entry_id, 99)
        legacy_ts, legacy_seq = decode_cursor(encode_cursor(ts, 3))
        self.assertEqual(legacy_ts, ts)
        self.assertEqual(legacy_seq, 3)

    def test_catch_up_preserves_stderr(self):
        from deployments.management.commands.run_log_collector import Command, RateWindow

        cmd = Command()
        cmd._persist_batch = MagicMock()

        out = b"2026-09-25T10:00:00.000000000Z out"
        err = b"2026-09-25T10:00:01.000000000Z err"
        raw = (
            bytes([1, 0, 0, 0]) + len(out).to_bytes(4, "big") + out +
            bytes([2, 0, 0, 0]) + len(err).to_bytes(4, "big") + err
        )
        container = SimpleNamespace(name="app-test", logs=MagicMock(return_value=raw))
        stream = SimpleNamespace(last_persisted_ts=None)
        service = SimpleNamespace(pk="service-1")

        from logs.policy import EffectiveLoggingPolicy
        policy = EffectiveLoggingPolicy(7, 1024 * 1024, 100_000, 16_384, True, False, "fifo_delete")
        cmd._catch_up(container, stream, service, policy, "collector-1", RateWindow(100_000))
        lines = cmd._persist_batch.call_args.args[4]
        self.assertEqual([item["stream"] for item in lines], ["stdout", "stderr"])
