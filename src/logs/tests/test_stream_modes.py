"""Regression coverage for runtime stream modes and recovery semantics."""
from __future__ import annotations

from datetime import timedelta
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
            max_entry_size=64,
            persistent_enabled=persistent,
            realtime_enabled=realtime,
            quota_behavior=behavior,
        )

    def test_effective_modes(self):
        self.assertEqual(self.policy().mode, "persistent_realtime")
        self.assertEqual(self.policy(realtime=False).mode, "persistent_only")
        self.assertEqual(self.policy(persistent=False).mode, "realtime_only")
        self.assertEqual(self.policy(persistent=False, realtime=False).mode, "disabled")
        self.assertEqual(self.policy(behavior="realtime_only").mode, "realtime_only")

    @patch("logs.realtime.publish_log_events")
    @patch("logs.ingestion.ingest_lines")
    def test_realtime_only_publishes_sanitized_ephemeral(self, mock_ingest, mock_publish):
        from deployments.management.commands.run_log_collector import Command

        mock_ingest.return_value = {
            "inserted": 0,
            "duplicates": 0,
            "dropped": 0,
            "bytes": 0,
            "persisted": False,
            "realtime_only": True,
            "inserted_entries": [],
            "realtime_lines": [{
                "ts": timezone.now(),
                "stream": "stderr",
                "message": "[REDACTED]",
                "byte_size": 10,
                "truncated": False,
                "level": "",
            }],
        }
        cmd = Command()
        cmd._buffer = MagicMock()
        service = SimpleNamespace(pk="service-1")
        stream = SimpleNamespace(pk=10, owner_id="collector-1", lease_until=timezone.now() + timedelta(seconds=30))

        cmd._persist_batch(
            "collector-1", service, stream, self.policy(persistent=False),
            [{"ts": timezone.now(), "stream": "stderr", "message": "secret"}],
        )

        mock_publish.assert_called_once()
        event = mock_publish.call_args.args[1][0]
        self.assertFalse(event["persisted"])
        self.assertTrue(event["ephemeral"])
        self.assertEqual(event["stream"], "stderr")
        self.assertEqual(event["message"], "[REDACTED]")
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
            "persisted": False,
            "inserted_entries": [],
            "realtime_lines": [
                {"ts": timezone.now(), "stream": "stdout", "message": "a", "byte_size": 1, "truncated": False, "level": ""},
                {"ts": timezone.now(), "stream": "stderr", "message": "b", "byte_size": 1, "truncated": False, "level": ""},
            ],
        }
        cmd = Command()
        cmd._buffer = MagicMock()
        service = SimpleNamespace(pk="service-1")
        stream = SimpleNamespace(pk=10, owner_id="collector-1", lease_until=timezone.now() + timedelta(seconds=30))

        cmd._persist_batch(
            "collector-1", service, stream, self.policy(behavior="drop_new"),
            [
                {"ts": timezone.now(), "stream": "stdout", "message": "a"},
                {"ts": timezone.now(), "stream": "stderr", "message": "b"},
            ],
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
            "realtime_lines": [],
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
            cmd._persist_batch("collector-1", service, stream, self.policy(), lines)

        mock_publish.assert_called_once()
        event = mock_publish.call_args.args[1][0]
        self.assertEqual(event["id"], 55)
        self.assertEqual(event["seq"], 7)
        self.assertEqual(event["stream"], "stderr")
        self.assertTrue(event["persisted"])

    @patch("logs.ingestion._redact", return_value="[REDACTED]")
    def test_non_persistent_ingestion_sanitizes_before_realtime(self, redact):
        from logs.ingestion import ingest_lines

        stream = SimpleNamespace(
            service_id="service-1",
            owner_id="collector-1",
            lease_until=timezone.now() + timedelta(seconds=30),
        )
        result = ingest_lines(
            stream,
            [{"ts": timezone.now(), "stream": "stderr", "message": "password=secret"}],
            policy=self.policy(persistent=False, realtime=True),
            owner_id="collector-1",
        )

        self.assertFalse(result["persisted"])
        self.assertEqual(result["realtime_lines"][0]["message"], "[REDACTED]")
        redact.assert_called_once_with("password=secret")

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

    def test_rate_window_is_shared_per_service(self):
        from deployments.management.commands.run_log_collector import Command

        cmd = Command()
        cmd._rate_windows = {}
        cmd._rate_lock = __import__("threading").Lock()
        service = SimpleNamespace(pk="service-1")

        first = cmd._rate_for_service(service, 100)
        second = cmd._rate_for_service(service, 200)

        self.assertIs(first, second)
        self.assertEqual(first.max_bps, 200)

    def test_partial_lines_are_reassembled(self):
        from deployments.management.commands.run_log_collector import DockerLineAssembler

        assembler = DockerLineAssembler()
        self.assertEqual(assembler.feed([("stdout", "hello ")]), [])
        self.assertEqual(assembler.feed([("stdout", "world\nnext")]), [("stdout", "hello world")])
        self.assertEqual(assembler.feed([("stderr", "error")]), [])
        self.assertEqual(assembler.flush(), [("stdout", "next"), ("stderr", "error")])

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
        policy = EffectiveLoggingPolicy(7, 1024 * 1024, 100_000, 64, True, False, "fifo_delete")
        cmd._catch_up(container, stream, service, policy, "collector-1", RateWindow(100_000))
        lines = cmd._persist_batch.call_args.args[4]
        self.assertEqual([item["stream"] for item in lines], ["stdout", "stderr"])
