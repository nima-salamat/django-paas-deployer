"""Authenticated, bounded HTTP ingestion endpoint for the Fluent Bit agent.

The endpoint intentionally has no user-session dependency: only the random
operator-owned shared token can submit records. Tenant identity is taken from
Docker's immutable container labels and revalidated against the Service table.
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import secrets
import threading
import time
from collections import OrderedDict, defaultdict
import re
from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

MAX_COMPRESSED_BYTES = 8 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 8 * 1024 * 1024
MAX_RECORDS_PER_REQUEST = 5000
MAX_RATE_WINDOWS = 10000


class _RateWindow:
    __slots__ = ("started", "used")

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.used = 0


class _PerServiceRateLimiter:
    """Process-local, per-service 1-second byte window with bounded state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: OrderedDict[str, _RateWindow] = OrderedDict()

    def filter(self, service_id: str, lines: list[dict], limit: int):
        accepted: list[dict] = []
        dropped_entries = 0
        dropped_bytes = 0
        now = time.monotonic()
        maximum = max(1024, int(limit))

        with self._lock:
            window = self._windows.get(service_id)
            if window is None or now - window.started >= 1.0:
                window = _RateWindow()
                self._windows[service_id] = window
            self._windows.move_to_end(service_id)

            for line in lines:
                size = len(str(line.get("message") or "").encode("utf-8", "replace"))
                if window.used + size > maximum:
                    dropped_entries += 1
                    dropped_bytes += size
                    continue
                window.used += size
                accepted.append(line)

            # Hard bound memory under churn from short-lived services.
            while len(self._windows) > MAX_RATE_WINDOWS:
                self._windows.popitem(last=False)

        return accepted, dropped_entries, dropped_bytes

    def refund(self, service_id: str, lines: list[dict]) -> None:
        """Refund a reservation when the database rejects a batch for retry."""
        byte_count = sum(
            len(str(line.get("message") or "").encode("utf-8", "replace"))
            for line in lines
        )
        if byte_count <= 0:
            return
        with self._lock:
            window = self._windows.get(service_id)
            if window is not None and time.monotonic() - window.started < 1.0:
                window.used = max(0, window.used - byte_count)
                self._windows.move_to_end(service_id)


_rate_limiter = _PerServiceRateLimiter()


def _bounded_body(request) -> bytes | None:
    raw_length = request.META.get("CONTENT_LENGTH")
    try:
        if raw_length and int(raw_length) > MAX_COMPRESSED_BYTES:
            return None
    except (TypeError, ValueError):
        return None

    try:
        # Read at most limit + 1 bytes directly from the request stream. This
        # avoids Django's generic form-upload size gate while keeping this
        # machine endpoint strictly bounded.
        body = request.read(MAX_COMPRESSED_BYTES + 1)
    except Exception:
        return None
    if len(body) > MAX_COMPRESSED_BYTES:
        return None

    encoding = (request.headers.get("Content-Encoding") or "").strip().lower()
    if encoding in {"", "identity"}:
        return body
    if encoding != "gzip":
        return None

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as stream:
            expanded = stream.read(MAX_DECOMPRESSED_BYTES + 1)
            if len(expanded) > MAX_DECOMPRESSED_BYTES:
                return None
            if stream.read(1):
                return None
        return expanded
    except (OSError, EOFError):
        return None


def _record_metadata(record: dict) -> dict:
    attrs = record.get("attrs")
    metadata = dict(attrs) if isinstance(attrs, dict) else {}
    # Docker's Fluentd driver places selected labels in extra attributes.
    # Accept both nested attrs and flattened representations for forward
    # compatibility with Fluent Bit/Forward encoder versions.
    for key in (
        "managed-by",
        "passdeployer.service",
        "passdeployer.deployment",
        "passdeployer.process",
        "service.id",
        "deployment.id",
    ):
        if key in record and key not in metadata:
            metadata[key] = record[key]
    return metadata


def _parse_record(record: dict):
    if not isinstance(record, dict):
        return None

    metadata = _record_metadata(record)
    managed_by = str(metadata.get("managed-by") or "").strip()
    service_value = (
        metadata.get("passdeployer.service")
        or metadata.get("service.id")
        or ""
    )
    try:
        service_id = str(UUID(str(service_value)))
    except (TypeError, ValueError, AttributeError):
        return None

    container_id = str(record.get("container_id") or "").strip().lower()
    if not (12 <= len(container_id) <= 128):
        return None
    if any(ch not in "0123456789abcdef" for ch in container_id):
        return None
    if managed_by != "django-paas-deployer":
        return None

    stream = str(record.get("source") or record.get("stream") or "stdout").lower()
    if stream not in {"stdout", "stderr"}:
        stream = "stdout"

    message = record.get("log")
    if message is None:
        message = record.get("message")
    if message is None:
        return None
    if isinstance(message, bytes):
        message = message.decode("utf-8", "replace")
    elif not isinstance(message, str):
        message = str(message)
    message = message.rstrip("\r\n")

    raw_ts = (
        record.get("timestamp")
        or record.get("time")
        or record.get("date")
    )
    ts = None
    if isinstance(raw_ts, datetime):
        ts = raw_ts
    elif raw_ts:
        timestamp_text = str(raw_ts).strip()
        # Fluent Bit may preserve nanosecond Docker timestamps. Django/Python
        # datetime only stores microseconds, so trim excess fractional digits
        # instead of silently replacing a valid event time with ingestion time.
        if timestamp_text.endswith("Z"):
            timestamp_text = timestamp_text[:-1] + "+00:00"
        match = re.match(
            r"^(.*?\.\d{6})\d+([+-]\d{2}:?\d{2})$",
            timestamp_text,
        )
        if match:
            timestamp_text = match.group(1) + match.group(2)
        ts = parse_datetime(timestamp_text)
    if ts is None:
        ts = timezone.now()
    elif timezone.is_naive(ts):
        ts = timezone.make_aware(ts, timezone.get_current_timezone())

    deploy_value = (
        metadata.get("passdeployer.deployment")
        or metadata.get("deployment.id")
        or ""
    )
    try:
        deploy_id = str(UUID(str(deploy_value))) if deploy_value else None
    except (TypeError, ValueError, AttributeError):
        deploy_id = None

    return {
        "service_id": service_id,
        "container_id": container_id,
        "container_name": str(record.get("container_name") or "")[:255],
        "deploy_id": deploy_id,
        "ts": ts,
        "stream": stream,
        "message": message,
    }


def _publish_batch(service_id: str, stream_id: int, result: dict, realtime: bool) -> None:
    if not realtime:
        return

    from logs.query import encode_cursor
    from logs.realtime import publish_log_events

    events = []
    for item in result.get("inserted_entries") or []:
        ts = item.get("ts")
        entry_id = item.get("id")
        seq = item.get("seq")
        if ts is None or entry_id is None or seq is None:
            continue
        events.append({
            "id": entry_id,
            "stream_id": stream_id,
            "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "seq": int(seq),
            "stream": item.get("stream") or "stdout",
            "level": item.get("level") or None,
            "message": item.get("message") or "",
            "byte_size": item.get("byte_size") or 0,
            "truncated": bool(item.get("truncated")),
            "cursor": encode_cursor(ts, int(seq), entry_id=int(entry_id)),
            "persisted": True,
        })

    if not events:
        for item in result.get("realtime_lines") or []:
            ts = item.get("ts")
            events.append({
                "id": None,
                "stream_id": stream_id,
                "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "seq": None,
                "stream": item.get("stream") or "stdout",
                "level": item.get("level") or None,
                "message": item.get("message") or "",
                "byte_size": item.get("byte_size") or 0,
                "truncated": bool(item.get("truncated")),
                "cursor": None,
                "persisted": False,
                "ephemeral": True,
            })

    if events:
        publish_log_events(service_id, events)


@csrf_exempt
@require_POST
def runtime_logs_ingest_apiview(request):
    """Receive one bounded JSON-lines batch from Fluent Bit."""
    expected = str(getattr(settings, "LOG_INGEST_SHARED_TOKEN", "") or "")
    supplied = str(request.headers.get("X-PassDeployer-Token") or "")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        return JsonResponse({"result": "error", "detail": "Unauthorized"}, status=401)

    body = _bounded_body(request)
    if body is None:
        return JsonResponse(
            {"result": "error", "detail": "Payload exceeds the configured limit or is invalid"},
            status=413,
        )
    if not body:
        return JsonResponse({"result": "success", "accepted": 0, "rejected": 0})

    try:
        lines = body.splitlines()
        if len(lines) > MAX_RECORDS_PER_REQUEST:
            return JsonResponse(
                {"result": "error", "detail": "Too many records in one batch"},
                status=413,
            )
        records = [json.loads(line) for line in lines if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"result": "error", "detail": "Invalid NDJSON payload"},
            status=400,
        )

    # Validate ownership metadata before any database lookup. Group by one
    # immutable container lifetime so one HTTP request becomes one DB batch
    # per container stream, not one transaction per log line.
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    rejected = 0
    for raw in records:
        parsed = _parse_record(raw)
        if parsed is None:
            rejected += 1
            continue
        grouped[(parsed["service_id"], parsed["container_id"])].append(parsed)

    if not grouped:
        return JsonResponse({
            "result": "success",
            "accepted": 0,
            "rejected": rejected,
        })

    from django.conf import settings as django_settings
    from django.utils import timezone
    from logs.ingestion import get_or_create_stream, ingest_lines
    from logs.models import CollectorHeartbeat
    from logs.policy import resolve
    from logs.usage import bump_drop
    from services.models import Service

    alias = getattr(django_settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"
    accepted_total = 0
    dropped_total = 0
    dropped_bytes_total = 0
    active_streams = 0
    service_cache = {}
    missing_service = object()

    for (service_id, container_id), records_for_stream in grouped.items():
        if service_id not in service_cache:
            service_cache[service_id] = (
                Service.objects.select_related("plan")
                .filter(pk=service_id)
                .first()
                or missing_service
            )
        service = service_cache[service_id]
        if service is missing_service:
            rejected += len(records_for_stream)
            continue

        policy = resolve(service)
        if not policy.persistent_enabled and not policy.realtime_enabled:
            rejected += len(records_for_stream)
            continue

        latest = records_for_stream[-1]
        stream = get_or_create_stream(
            service_id=service_id,
            container_id=container_id,
            container_name=latest["container_name"],
            deploy_id=latest["deploy_id"] or getattr(service, "selected_deploy_id", None),
        )
        active_streams += 1

        raw_lines = [
            {"ts": item["ts"], "stream": item["stream"], "message": item["message"]}
            for item in records_for_stream
        ]
        accepted_lines, dropped_entries, dropped_bytes = _rate_limiter.filter(
            service_id,
            raw_lines,
            policy.max_bytes_per_second,
        )
        if dropped_entries:
            try:
                bump_drop(
                    service_id,
                    entries=dropped_entries,
                    bytes_dropped=dropped_bytes,
                )
            except DatabaseError:
                logger.exception("Unable to record dropped runtime logs service=%s", service_id)
            dropped_total += dropped_entries
            dropped_bytes_total += dropped_bytes

        if not accepted_lines:
            continue

        try:
            result = ingest_lines(stream, accepted_lines, policy=policy)
            dropped_total += int(result.get("dropped") or 0)
            dropped_bytes_total += int(result.get("dropped_bytes") or 0)
            # Count accepted input records, including realtime-only/drop-new
            # modes where nothing is written to PostgreSQL by policy.
            accepted_total += len(accepted_lines)
            _publish_batch(
                service_id,
                stream.pk,
                result,
                realtime=bool(policy.realtime_enabled),
            )
        except Exception:
            # The reservation is not a committed ingestion. Refund it before
            # returning 503 so Fluent Bit's retry is not rejected by our own
            # in-memory rate limiter.
            _rate_limiter.refund(service_id, accepted_lines)
            # A 5xx tells Fluent Bit to retry the chunk; PostgreSQL uniqueness
            # makes a retry idempotent after successful/partial persistence.
            logger.exception(
                "Runtime log batch ingestion failed service=%s stream=%s",
                service_id,
                stream.pk,
            )
            return JsonResponse(
                {"result": "error", "detail": "Batch ingestion failed"},
                status=503,
            )

    collector_id = (
        str(request.headers.get("X-PassDeployer-Collector") or "fluent-bit")
        .strip()[:64]
        or "fluent-bit"
    )
    try:
        CollectorHeartbeat.objects.using(alias).update_or_create(
            instance_id=collector_id,
            defaults={
                "status": "healthy",
                "last_heartbeat": timezone.now(),
                "last_successful_ingestion": timezone.now(),
                "active_streams": active_streams,
                "active_containers": active_streams,
                "db_ok": True,
                "redis_ok": True,
                "last_error": "",
            },
        )
    except DatabaseError:
        logger.debug("Unable to update Fluent Bit heartbeat", exc_info=True)

    return JsonResponse({
        "result": "success",
        "accepted": accepted_total,
        "rejected": rejected,
        "dropped": dropped_total,
        "dropped_bytes": dropped_bytes_total,
        "streams": active_streams,
    })
