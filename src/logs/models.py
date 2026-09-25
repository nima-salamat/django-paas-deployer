"""
Runtime log persistence on DEPLOYMENT_LOG_DB_ALIAS.

No cross-database FK constraints (same pattern as DeployLog).
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ServiceLogStream(models.Model):
    """One container lifetime for a service."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        CLOSED = "closed", _("Closed")
        LOST = "lost", _("Lost")

    id = models.BigAutoField(primary_key=True)
    service_id = models.UUIDField(db_index=True)
    deploy_id = models.UUIDField(null=True, blank=True, db_index=True)
    container_id = models.CharField(max_length=128, db_index=True)
    container_name = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    # Docker recovery checkpoint (NOT application seq)
    last_persisted_ts = models.DateTimeField(null=True, blank=True)
    last_persisted_fingerprint = models.CharField(max_length=64, blank=True, default="")
    last_seq = models.BigIntegerField(default=0)

    # Stream ownership / lease
    owner_id = models.CharField(max_length=64, blank=True, default="")
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.CharField(max_length=64, blank=True, default="")
    heartbeat_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "logs"
        indexes = [
            models.Index(fields=["service_id", "-started_at"]),
            models.Index(fields=["container_id", "status"]),
        ]

    def __str__(self):
        return f"Stream {self.id} service={self.service_id} container={self.container_name}"


class ServiceLogEntry(models.Model):
    """Append-only runtime log line."""

    class StreamKind(models.TextChoices):
        STDOUT = "stdout", _("stdout")
        STDERR = "stderr", _("stderr")

    id = models.BigAutoField(primary_key=True)
    service_id = models.UUIDField(db_index=True)
    stream_id = models.BigIntegerField(db_index=True)
    deploy_id = models.UUIDField(null=True, blank=True)
    ts = models.DateTimeField(db_index=True)
    seq = models.BigIntegerField()
    stream = models.CharField(max_length=8, choices=StreamKind.choices, default=StreamKind.STDOUT)
    level = models.CharField(max_length=16, blank=True, default="", db_index=True)
    message = models.TextField()
    byte_size = models.PositiveIntegerField(default=0)
    truncated = models.BooleanField(default=False)
    # Dedup identity for recovery overlap (sha256 hex of ts|stream|message)
    fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "logs"
        constraints = [
            models.UniqueConstraint(fields=["stream_id", "seq"], name="uniq_log_stream_seq"),
            models.UniqueConstraint(
                fields=["stream_id", "fingerprint"],
                name="uniq_log_stream_fingerprint",
                condition=~models.Q(fingerprint=""),
            ),
        ]
        indexes = [
            models.Index(fields=["service_id", "-ts", "-seq"], name="svc_log_ts_seq_idx"),
            models.Index(fields=["service_id", "stream", "-ts"], name="svc_log_stream_ts_idx"),
            models.Index(fields=["service_id", "level", "-ts"], name="svc_log_level_ts_idx"),
        ]

    def __str__(self):
        return f"LogEntry {self.id} svc={self.service_id} seq={self.seq}"


class ServiceLogUsage(models.Model):
    """Per-service incremental usage counters."""

    service_id = models.UUIDField(primary_key=True)
    current_storage_bytes = models.BigIntegerField(default=0)
    entry_count = models.BigIntegerField(default=0)
    entries_dropped = models.BigIntegerField(default=0)
    bytes_dropped = models.BigIntegerField(default=0)
    last_ingestion_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "logs"

    def __str__(self):
        return f"Usage {self.service_id} bytes={self.current_storage_bytes}"


class LogUsageDaily(models.Model):
    """Daily aggregates for admin trends."""

    id = models.BigAutoField(primary_key=True)
    service_id = models.UUIDField(db_index=True)
    date = models.DateField(db_index=True)
    bytes_ingested = models.BigIntegerField(default=0)
    entries_ingested = models.BigIntegerField(default=0)
    bytes_deleted = models.BigIntegerField(default=0)
    entries_deleted = models.BigIntegerField(default=0)
    entries_dropped = models.BigIntegerField(default=0)
    bytes_dropped = models.BigIntegerField(default=0)

    class Meta:
        app_label = "logs"
        constraints = [
            models.UniqueConstraint(fields=["service_id", "date"], name="uniq_log_usage_daily"),
        ]

    def __str__(self):
        return f"Daily {self.service_id} {self.date}"


class CollectorHeartbeat(models.Model):
    """Single-row-style health for admin (one row per collector instance)."""

    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=32, default="healthy")
    last_heartbeat = models.DateTimeField(default=timezone.now)
    last_successful_ingestion = models.DateTimeField(null=True, blank=True)
    active_streams = models.PositiveIntegerField(default=0)
    active_containers = models.PositiveIntegerField(default=0)
    buffer_bytes = models.BigIntegerField(default=0)
    dropped_entries = models.BigIntegerField(default=0)
    dropped_bytes = models.BigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    db_ok = models.BooleanField(default=True)
    redis_ok = models.BooleanField(default=True)
    meta = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "logs"
