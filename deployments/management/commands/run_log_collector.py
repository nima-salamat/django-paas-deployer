"""
Long-lived runtime log collector: discover → lease → catch-up → live follow.

Celery is NOT used for continuous ingestion.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

MAX_FOLLOW_WORKERS = int(os.environ.get("LOG_COLLECTOR_WORKERS", "8"))
BUFFER_MAX_BYTES = int(os.environ.get("LOG_COLLECTOR_BUFFER_BYTES", str(8 * 1024 * 1024)))


def _instance_id() -> str:
    return os.environ.get("LOG_COLLECTOR_ID") or f"{socket.gethostname()}-{os.getpid()}"


class RateWindow:
    def __init__(self, max_bps: int):
        self.max_bps = max(1024, int(max_bps))
        self.window_start = time.monotonic()
        self.bytes_in_window = 0
        self._lock = threading.Lock()

    def allow(self, n: int) -> bool:
        with self._lock:
            now = time.monotonic()
            if now - self.window_start >= 1.0:
                self.window_start = now
                self.bytes_in_window = 0
            if self.bytes_in_window + n > self.max_bps:
                return False
            self.bytes_in_window += n
            return True


class BoundedBuffer:
    """In-memory fallback when log DB is unavailable."""

    def __init__(self, max_bytes: int = BUFFER_MAX_BYTES):
        self.max_bytes = max_bytes
        self._items: list = []
        self._bytes = 0
        self._lock = threading.Lock()
        self.dropped_entries = 0
        self.dropped_bytes = 0

    def push(self, service_id, stream_id, lines: list) -> None:
        with self._lock:
            for line in lines:
                size = sum(len(str(line.get("message") or "").encode()) for _ in [0])
                size = len(str(line.get("message") or "").encode("utf-8", "replace"))
                while self._bytes + size > self.max_bytes and self._items:
                    old = self._items.pop(0)
                    ob = len(str(old[2][0].get("message") if old[2] else "").encode("utf-8", "replace"))
                    self._bytes = max(0, self._bytes - ob)
                    self.dropped_entries += 1
                    self.dropped_bytes += ob
                if self._bytes + size > self.max_bytes:
                    self.dropped_entries += 1
                    self.dropped_bytes += size
                    continue
                self._items.append((service_id, stream_id, [line]))
                self._bytes += size

    def drain(self) -> list:
        with self._lock:
            items = self._items
            self._items = []
            self._bytes = 0
            return items

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self._bytes


class Command(BaseCommand):
    help = "Host-level runtime log collector (catch-up + live follow)."

    def add_arguments(self, parser):
        parser.add_argument("--poll", type=float, default=10.0, help="Rediscovery interval")
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        instance = _instance_id()
        self.stdout.write(self.style.SUCCESS(f"Log collector instance={instance} workers={MAX_FOLLOW_WORKERS}"))
        self._stop = threading.Event()
        self._following: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._buffer = BoundedBuffer()
        self._executor = ThreadPoolExecutor(max_workers=MAX_FOLLOW_WORKERS, thread_name_prefix="log-follow")
        backoff = 1.0
        try:
            while not self._stop.is_set():
                try:
                    self._flush_buffer()
                    self._discover_and_attach(instance)
                    self._heartbeat(instance, "healthy", "")
                    backoff = 1.0
                except Exception as exc:
                    logger.exception("collector cycle error")
                    self._heartbeat(instance, "degraded", str(exc)[:500])
                    time.sleep(min(backoff, 60))
                    backoff = min(backoff * 2, 60)
                    continue
                if options["once"]:
                    break
                self._stop.wait(max(2.0, float(options["poll"])))
        finally:
            self._stop.set()
            for ev in list(self._following.values()):
                ev.set()
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _heartbeat(self, instance: str, status: str, error: str):
        try:
            from django.conf import settings
            from logs.models import CollectorHeartbeat

            alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
            with self._lock:
                active = len(self._following)
            CollectorHeartbeat.objects.using(alias).update_or_create(
                instance_id=instance,
                defaults={
                    "status": status,
                    "last_heartbeat": timezone.now(),
                    "last_error": error or "",
                    "active_streams": active,
                    "active_containers": active,
                    "buffer_bytes": self._buffer.size_bytes,
                    "dropped_entries": self._buffer.dropped_entries,
                    "dropped_bytes": self._buffer.dropped_bytes,
                    "db_ok": status != "disconnected",
                    "redis_ok": True,
                },
            )
        except Exception:
            logger.debug("heartbeat failed", exc_info=True)

    def _flush_buffer(self):
        from logs.models import ServiceLogStream
        from logs.ingestion import ingest_lines
        from logs.policy import resolve_for_service_id
        from django.conf import settings

        items = self._buffer.drain()
        if not items:
            return
        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
        for service_id, stream_id, lines in items:
            try:
                stream = ServiceLogStream.objects.using(alias).filter(pk=stream_id).first()
                if not stream:
                    continue
                policy = resolve_for_service_id(service_id)
                ingest_lines(stream, lines, policy=policy)
            except Exception:
                logger.debug("buffer flush failed", exc_info=True)
                self._buffer.push(service_id, stream_id, lines)

    def _discover_and_attach(self, instance: str):
        from deployments.core.manager.client_manager import get_docker_client
        from services.models import Service
        from logs.ingestion import acquire_lease, get_or_create_stream
        from logs.policy import resolve

        client = get_docker_client()
        containers = client.containers.list(all=False)
        services = list(Service.objects.select_related("plan").all()[:5000])
        name_map = {}
        for s in services:
            try:
                name_map[s.get_docker_service_name()] = s
            except Exception:
                continue

        seen_cids = set()
        for c in containers:
            name = (c.name or "").lstrip("/")
            service = name_map.get(name)
            if not service:
                continue
            policy = resolve(service)
            if not policy.persistent_enabled and not policy.realtime_enabled:
                continue
            cid = c.id
            seen_cids.add(cid)
            with self._lock:
                if cid in self._following:
                    continue
                stop_ev = threading.Event()
                self._following[cid] = stop_ev
            stream = get_or_create_stream(
                service_id=service.pk,
                container_id=cid,
                container_name=name,
            )
            if not acquire_lease(stream, instance):
                with self._lock:
                    self._following.pop(cid, None)
                continue
            self._executor.submit(
                self._follow_container, instance, service, c, stream, policy, stop_ev
            )

        # Stop followers for gone containers
        with self._lock:
            stale = [cid for cid in self._following if cid not in seen_cids]
            for cid in stale:
                self._following.pop(cid).set()

    def _follow_container(self, instance, service, container, stream, policy, stop_ev: threading.Event):
        from logs.ingestion import (
            ingest_lines,
            heartbeat_lease,
            close_stream,
        )
        from logs.realtime import publish_log_events
        from logs.query import encode_cursor
        from logs.usage import bump_drop
        from logs.models import ServiceLogStream

        rate = RateWindow(policy.max_bytes_per_second)
        cid = container.id
        try:
            # ---- Catch-up ----
            self._catch_up(container, stream, service, policy, instance, rate)
            # ---- Live follow ----
            try:
                log_stream = container.logs(
                    stream=True,
                    follow=True,
                    stdout=True,
                    stderr=True,
                    timestamps=True,
                    tail=0,
                )
            except Exception as exc:
                logger.warning("follow start failed %s: %s", container.name, exc)
                return

            batch = []
            last_hb = time.monotonic()
            last_flush = time.monotonic()
            try:
                for raw in log_stream:
                    if stop_ev.is_set() or self._stop.is_set():
                        break
                    if isinstance(raw, (bytes, bytearray)):
                        pairs = self._demux_docker_chunk(raw)
                    else:
                        pairs = [("stdout", str(raw))]
                    for stream_kind, line in pairs:
                        if not line:
                            continue
                        ts, msg = self._parse_ts_line(line)
                        # if parse already ate ts prefix, stream still from demux
                        size = len(msg.encode("utf-8", "replace"))
                        if not rate.allow(size):
                            bump_drop(service.pk, entries=1, bytes_dropped=size)
                            continue
                        batch.append(
                            {
                                "ts": ts or timezone.now(),
                                "stream": stream_kind,
                                "message": msg,
                            }
                        )
                    now = time.monotonic()
                    if batch and (len(batch) >= 50 or now - last_flush >= 1.0):
                        self._persist_batch(instance, service, stream, policy, batch)
                        batch = []
                        last_flush = now
                    if now - last_hb >= 15:
                        if not heartbeat_lease(stream, instance):
                            logger.info("lost lease stream=%s", stream.pk)
                            break
                        last_hb = now
            finally:
                if batch:
                    self._persist_batch(instance, service, stream, policy, batch)
                try:
                    log_stream.close()
                except Exception:
                    pass
        except Exception:
            logger.exception("follow crashed container=%s", getattr(container, "name", cid))
        finally:
            with self._lock:
                self._following.pop(cid, None)
            try:
                # Only close if container is gone
                container.reload()
                if container.status not in {"running", "created"}:
                    close_stream(stream, status=ServiceLogStream.Status.CLOSED)
            except Exception:
                close_stream(stream, status=ServiceLogStream.Status.LOST)

    def _catch_up(self, container, stream, service, policy, instance, rate: RateWindow):
        try:
            raw = container.logs(
                stdout=True, stderr=True, timestamps=True, tail=1000
            )
        except Exception as exc:
            logger.warning("catch-up failed %s: %s", container.name, exc)
            return
        text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
        lines = []
        skew = stream.last_persisted_ts - timedelta(seconds=5) if stream.last_persisted_ts else None
        for line in text.splitlines():
            ts, msg = self._parse_ts_line(line)
            if skew and ts and ts < skew:
                continue
            size = len(msg.encode("utf-8", "replace"))
            if not rate.allow(size):
                continue
            lines.append({"ts": ts or timezone.now(), "stream": "stdout", "message": msg})
        if lines:
            self._persist_batch(instance, service, stream, policy, lines)

    def _persist_batch(self, instance, service, stream, policy, lines: list):
        from logs.ingestion import ingest_lines
        from logs.realtime import publish_log_events
        from logs.query import encode_cursor

        try:
            result = ingest_lines(stream, lines, policy=policy, owner_id=instance)
        except Exception:
            logger.warning("persist failed, buffering", exc_info=True)
            self._buffer.push(service.pk, stream.pk, lines)
            return
        if not result.get("inserted") or not policy.realtime_enabled:
            return
        n = int(result.get("inserted") or 0)
        events = []
        seq = int(stream.last_seq or 0) - n
        for item in lines[-n:]:
            seq += 1
            ts = item["ts"]
            events.append(
                {
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "seq": seq,
                    "stream": item.get("stream") or "stdout",
                    "message": item.get("message") or "",
                    "cursor": encode_cursor(ts, seq) if hasattr(ts, "isoformat") else None,
                }
            )
        publish_log_events(service.pk, events)
        try:
            from django.conf import settings
            from logs.models import CollectorHeartbeat

            alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
            CollectorHeartbeat.objects.using(alias).filter(instance_id=instance).update(
                last_successful_ingestion=timezone.now()
            )
        except Exception:
            pass


    def _demux_docker_chunk(self, raw: bytes):
        """Split Docker multiplexed stream into (stream_kind, text) lines.

        Non-TTY: 8-byte header (stream 1=stdout 2=stderr) + payload.
        TTY/raw: treat as stdout lines.
        """
        if not raw:
            return []
        out = []
        # Heuristic: if looks multiplexed
        if len(raw) >= 8 and raw[0] in (1, 2) and raw[1:4] == b"\x00\x00\x00":
            i = 0
            while i + 8 <= len(raw):
                stream_type = raw[i]
                size = int.from_bytes(raw[i + 4 : i + 8], "big")
                i += 8
                payload = raw[i : i + size]
                i += size
                kind = "stderr" if stream_type == 2 else "stdout"
                text = payload.decode("utf-8", "replace")
                for line in text.splitlines():
                    if line:
                        out.append((kind, line))
            return out
        text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        for line in text.splitlines():
            if line:
                out.append(("stdout", line))
        return out

    def _parse_ts_line(self, line: str):
        if len(line) > 30 and line[0:4].isdigit() and "T" in line[:30]:
            parts = line.split(" ", 1)
            raw_ts = parts[0].replace("Z", "+00:00")
            # trim nanoseconds for parse_datetime
            if "." in raw_ts:
                head, rest = raw_ts.split(".", 1)
                frac = "".join(ch for ch in rest if ch.isdigit())[:6]
                tz = ""
                for i, ch in enumerate(rest):
                    if ch in "+-":
                        tz = rest[i:]
                        break
                raw_ts = f"{head}.{frac}{tz or '+00:00'}"
            ts = parse_datetime(raw_ts)
            if ts and timezone.is_naive(ts):
                ts = timezone.make_aware(ts, timezone.utc)
            msg = parts[1] if len(parts) > 1 else ""
            return ts, msg
        return None, line
