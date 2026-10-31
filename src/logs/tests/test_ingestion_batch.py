from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from logs.ingestion import ingest_lines
from logs.models import LogUsageDaily, ServiceLogEntry, ServiceLogStream, ServiceLogUsage
from logs.policy import EffectiveLoggingPolicy


class BulkRuntimeLogIngestionTests(TestCase):
    databases = {"default", "deployment_logs"}

    def setUp(self):
        self.service_id = uuid4()
        self.stream = ServiceLogStream.objects.using("deployment_logs").create(
            service_id=self.service_id,
            container_id="a" * 64,
            container_name="app-test",
        )
        self.policy = EffectiveLoggingPolicy(
            retention_days=7,
            storage_quota_bytes=16 * 1024 * 1024,
            max_bytes_per_second=1024 * 1024,
            max_entry_size=4096,
            persistent_enabled=True,
            realtime_enabled=True,
            quota_behavior="fifo_delete",
        )

    def test_bulk_batch_deduplicates_without_aborting_transaction(self):
        ts = timezone.now()
        lines = [
            {"ts": ts, "stream": "stdout", "message": "first"},
            {"ts": ts, "stream": "stderr", "message": "same timestamp, other stream"},
            {"ts": ts, "stream": "stdout", "message": "first"},
        ]

        result = ingest_lines(self.stream, lines, policy=self.policy)

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(
            ServiceLogEntry.objects.using("deployment_logs")
            .filter(stream_id=self.stream.pk)
            .count(),
            2,
        )

        replay = ingest_lines(self.stream, lines, policy=self.policy)
        self.assertEqual(replay["inserted"], 0)
        self.assertEqual(replay["duplicates"], 3)
        self.assertEqual(
            ServiceLogEntry.objects.using("default")
            .filter(stream_id=self.stream.pk)
            .count(),
            2,
        )

        usage = ServiceLogUsage.objects.using("default").get(service_id=self.service_id)
        expected_bytes = sum(
            len(message.encode("utf-8"))
            for message in ("first", "same timestamp, other stream")
        )
        self.assertEqual(usage.entry_count, 2)
        self.assertEqual(usage.current_storage_bytes, expected_bytes)

        daily = LogUsageDaily.objects.using("default").get(
            service_id=self.service_id,
            date=timezone.localdate(),
        )
        self.assertEqual(daily.entries_ingested, 2)
        self.assertEqual(daily.bytes_ingested, expected_bytes)

    def test_replayed_batch_does_not_consume_quota_twice(self):
        policy = EffectiveLoggingPolicy(
            retention_days=7,
            storage_quota_bytes=5,
            max_bytes_per_second=1024,
            max_entry_size=4096,
            persistent_enabled=True,
            realtime_enabled=True,
            quota_behavior="drop_new",
        )
        line = {"ts": timezone.now(), "stream": "stdout", "message": "hello"}
        first = ingest_lines(self.stream, [line], policy=policy)
        replay = ingest_lines(self.stream, [line], policy=policy)

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(replay["inserted"], 0)
        self.assertEqual(replay["duplicates"], 1)
        self.assertEqual(replay["dropped"], 0)
        usage = ServiceLogUsage.objects.using("deployment_logs").get(
            service_id=self.service_id
        )
        self.assertEqual(usage.entry_count, 1)
        self.assertEqual(usage.current_storage_bytes, 5)

    def test_duplicate_inside_one_batch_leaves_monotonic_sequence_with_gap(self):
        ts = timezone.now()
        line = {"ts": ts, "stream": "stdout", "message": "same"}
        result = ingest_lines(
            self.stream,
            [line, line, line],
            policy=self.policy,
        )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["duplicates"], 2)
        row = ServiceLogEntry.objects.using("default").get(stream_id=self.stream.pk)
        self.assertEqual(row.seq, 1)
        self.stream.refresh_from_db(using="deployment_logs")
        self.assertEqual(self.stream.last_seq, 3)
