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

from deployments.core.swarm import SwarmRuntime, swarm_enabled

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


class DockerLineAssembler:
    """Reassembles Docker log chunks so line boundaries survive streaming."""
    
    def __init__(self):
        self._buffers = {"stdout": "", "stderr": ""}

    def feed(self, pairs):
        complete = []
        for kind, chunk in pairs:
            if kind not in self._buffers:
                kind = "stdout"
            text = self._buffers[kind] + (chunk or "")
            parts = text.split("\n")
            self._buffers[kind] = parts.pop()
            for line in parts:
                line = line.rstrip("\r")
                if line:
                    complete.append((kind, line))
        return complete

    def flush(self):
        complete = []
        for kind, text in list(self._buffers.items()):
            text = text.rstrip("\r")
            if text:
                complete.append((kind, text))
            self._buffers[kind] = ""
        return complete


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
        self._rate_windows: dict[str, RateWindow] = {}
        self._rate_lock = threading.Lock()
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

    def _rate_for_service(self, service, max_bps: int) -> RateWindow:
        """Return one rate window shared by all streams of a service in this collector."""
        key = str(service.pk)
        with getattr(self, "_rate_lock", threading.Lock()):
            windows = getattr(self, "_rate_windows", None)
            if windows is None:
                windows = {}
                self._rate_windows = windows
                self._rate_lock = getattr(self, "_rate_lock", threading.Lock())
            rate = windows.get(key)
            if rate is None:
                rate = RateWindow(max_bps)
                windows[key] = rate
            else:
                rate.max_bps = max(1024, int(max_bps))
            return rate

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
        from logs.ingestion import acquire_lease
        from logs.policy import resolve
        from services.models import Service
        from django.conf import settings

        items = self._buffer.drain()
        if not items:
            return
        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
        instance = _instance_id()
        for service_id, stream_id, lines in items:
            try:
                stream = ServiceLogStream.objects.using(alias).filter(pk=stream_id).first()
                service = Service.objects.select_related("plan").filter(pk=service_id).first()
                if not stream or not service:
                    continue
                if not acquire_lease(stream, instance):
                    # Preserve single-writer ownership; this collector is no longer owner.
                    continue
                policy = resolve(service)
                self._persist_batch(instance, service, stream, policy, lines)
            except Exception:
                logger.debug("buffer flush failed", exc_info=True)
                self._buffer.push(service_id, stream_id, lines)

    def _resolve_service_for_container(self, container, name_map, hex_map, services_by_id):
        """Map a running container to a Service using name, labels, then hex id."""
        name = (getattr(container, "name", None) or "").lstrip("/")
        # 1) Exact docker service name
        svc = name_map.get(name)
        if svc:
            return svc
        # 2) Labels (if platform set them)
        try:
            labels = (container.labels or {}) if hasattr(container, "labels") else {}
            if not labels and hasattr(container, "attrs"):
                labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        except Exception:
            labels = {}
        for key in ("service.id", "service_id", "paas.service_id"):
            raw = labels.get(key)
            if raw and str(raw) in services_by_id:
                return services_by_id[str(raw)]
        # 3) Name pattern app-{8 hex}-{rest} from get_docker_service_name
        if name.startswith("app-") and len(name) > 12:
            hex8 = name[4:12]
            if hex8 in hex_map:
                return hex_map[hex8]
        # 4) Prefix match (recreate suffixes rare but possible)
        for expected, svc in name_map.items():
            if name == expected or name.startswith(expected + "-"):
                return svc
        return None

    def _discover_and_attach_swarm(self, instance: str):
        from services.models import Service
        from logs.ingestion import acquire_lease, get_or_create_stream
        from logs.policy import resolve

        runtime = SwarmRuntime()
        client = runtime.client
        services = list(Service.objects.select_related("plan").all()[:5000])
        services_by_id = {str(service.pk): service for service in services}

        try:
            swarm_services = client.services.list(
                filters={"label": "managed-by=django-paas-deployer"}
            )
        except Exception:
            logger.exception("Swarm service discovery failed")
            return

        seen_keys: set[str] = set()
        matched = 0
        for docker_service in swarm_services:
            attrs = docker_service.attrs or {}
            spec = attrs.get("Spec") or {}
            labels = spec.get("Labels") or {}
            service_id = str(labels.get("passdeployer.service") or "")
            if not service_id or service_id not in services_by_id:
                continue
            service = services_by_id[service_id]
            try:
                policy = resolve(service)
            except Exception:
                logger.exception("policy resolve failed service=%s", service.pk)
                continue
            if not policy.persistent_enabled and not policy.realtime_enabled:
                continue

            key = f"swarm:{docker_service.id}"
            seen_keys.add(key)
            matched += 1
            with self._lock:
                if key in self._following:
                    continue
                stop_ev = threading.Event()
                self._following[key] = stop_ev

            deploy_id = labels.get("passdeployer.deployment") or getattr(service, "selected_deploy_id", None)
            stream = get_or_create_stream(
                service_id=service.pk,
                container_id=str(docker_service.id),
                container_name=str(docker_service.name),
                deploy_id=deploy_id,
            )
            if not acquire_lease(stream, instance):
                with self._lock:
                    self._following.pop(key, None)
                continue

            self._executor.submit(
                self._follow_swarm_service,
                instance,
                service,
                docker_service,
                stream,
                policy,
                stop_ev,
                key,
            )

        with self._lock:
            stale = [key for key in self._following if key.startswith("swarm:") and key not in seen_keys]
            for key in stale:
                self._following.pop(key).set()

        logger.info(
            "log-collector swarm discover: services=%s matched=%s following=%s",
            len(swarm_services),
            matched,
            len(self._following),
        )

    def _follow_swarm_service(
        self,
        instance,
        service,
        docker_service,
        stream,
        policy,
        stop_ev,
        key,
    ):
        from logs.ingestion import ingest_lines, heartbeat_lease, close_stream
        from logs.usage import bump_drop

        rate = self._rate_for_service(service, policy.max_bytes_per_second)
        try:
            self._catch_up(docker_service, stream, service, policy, instance, rate)
            log_stream = docker_service.logs(
                stream=True,
                follow=True,
                stdout=True,
                stderr=True,
                timestamps=True,
                tail=0,
            )
            batch = []
            assembler = DockerLineAssembler()
            last_hb = time.monotonic()
            last_flush = time.monotonic()
            try:
                for raw in log_stream:
                    if stop_ev.is_set() or self._stop.is_set():
                        break
                    pairs = (
                        self._demux_docker_payloads(raw)
                        if isinstance(raw, (bytes, bytearray))
                        else [("stdout", str(raw))]
                    )
                    for stream_kind, line in assembler.feed(pairs):
                        ts, msg = self._parse_ts_line(line)
                        size = len(msg.encode("utf-8", "replace"))
                        if not rate.allow(size):
                            bump_drop(service.pk, entries=1, bytes_dropped=size)
                            continue
                        batch.append({
                            "ts": ts or timezone.now(),
                            "stream": stream_kind,
                            "message": msg,
                        })
                    now = time.monotonic()
                    if batch and (len(batch) >= 50 or now - last_flush >= 1.0):
                        self._persist_batch(instance, service, stream, policy, batch)
                        batch = []
                        last_flush = now
                    if now - last_hb >= 15:
                        if not heartbeat_lease(stream, instance):
                            break
                        last_hb = now
            finally:
                for stream_kind, line in assembler.flush():
                    ts, msg = self._parse_ts_line(line)
                    size = len(msg.encode("utf-8", "replace"))
                    if rate.allow(size):
                        batch.append({
                            "ts": ts or timezone.now(),
                            "stream": stream_kind,
                            "message": msg,
                        })
                    else:
                        bump_drop(service.pk, entries=1, bytes_dropped=size)
                if batch:
                    self._persist_batch(instance, service, stream, policy, batch)
                try:
                    log_stream.close()
                except Exception:
                    pass
        except Exception:
            logger.exception(
                "Swarm service log follow crashed service=%s swarm_service=%s",
                service.pk,
                getattr(docker_service, "name", key),
            )
        finally:
            with self._lock:
                self._following.pop(key, None)
            try:
                close_stream(stream, status="closed", owner_id=instance)
            except Exception:
                pass

    def _discover_and_attach(self, instance: str):
        if swarm_enabled():
            self._discover_and_attach_swarm(instance)
            return

        from deployments.core.manager.client_manager import get_docker_client
        from services.models import Service
        from logs.ingestion import acquire_lease, get_or_create_stream
        from logs.policy import resolve

        client = get_docker_client()
        # Prefer managed platform containers (same label as event consumer)
        try:
            containers = client.containers.list(
                all=False,
                filters={"label": ["managed-by=django-paas-deployer"]},
            )
        except Exception:
            logger.warning("label filter list failed; falling back to all running", exc_info=True)
            containers = client.containers.list(all=False)

        services = list(Service.objects.select_related("plan").all()[:5000])
        name_map = {}
        hex_map = {}
        services_by_id = {}
        for s in services:
            try:
                dname = s.get_docker_service_name()
                name_map[dname] = s
                name_map[dname.lower()] = s
                hex_map[s.id.hex[:8]] = s
                services_by_id[str(s.pk)] = s
                services_by_id[s.id.hex] = s
            except Exception:
                continue

        logger.info(
            "log-collector discover: managed_containers=%s services=%s following=%s",
            len(containers),
            len(services),
            len(self._following),
        )

        seen_cids = set()
        matched = 0
        for c in containers:
            name = (c.name or "").lstrip("/")
            service = self._resolve_service_for_container(c, name_map, hex_map, services_by_id)
            if not service:
                logger.debug("log-collector skip unmatched container name=%s", name)
                continue
            matched += 1
            try:
                policy = resolve(service)
            except Exception:
                logger.exception("policy resolve failed service=%s", service.pk)
                continue
            if not policy.persistent_enabled and not policy.realtime_enabled:
                logger.info("logging disabled by policy service=%s", service.pk)
                continue
            cid = c.id
            seen_cids.add(cid)
            with self._lock:
                if cid in self._following:
                    continue
                stop_ev = threading.Event()
                self._following[cid] = stop_ev
            deploy_id = None
            try:
                deploy_id = getattr(service, "selected_deploy_id", None) or getattr(
                    service, "active_deploy_id", None
                )
            except Exception:
                deploy_id = None
            stream = get_or_create_stream(
                service_id=service.pk,
                container_id=cid,
                container_name=name,
                deploy_id=deploy_id,
            )
            if not acquire_lease(stream, instance):
                logger.info("lease denied stream=%s container=%s", stream.pk, name)
                with self._lock:
                    self._following.pop(cid, None)
                continue
            logger.info(
                "log-collector attach service=%s container=%s stream=%s",
                service.pk,
                name,
                stream.pk,
            )
            self._executor.submit(
                self._follow_container, instance, service, c, stream, policy, stop_ev
            )

        logger.info("log-collector discover done matched=%s attached_new_check following=%s", matched, len(self._following))

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

        rate = self._rate_for_service(service, policy.max_bytes_per_second)
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
                time.sleep(2)
                return

            batch = []
            assembler = DockerLineAssembler()
            last_hb = time.monotonic()
            last_flush = time.monotonic()
            try:
                for raw in log_stream:
                    if stop_ev.is_set() or self._stop.is_set():
                        break
                    pairs = (
                        self._demux_docker_payloads(raw)
                        if isinstance(raw, (bytes, bytearray))
                        else [("stdout", str(raw))]
                    )
                    for stream_kind, line in assembler.feed(pairs):
                        ts, msg = self._parse_ts_line(line)
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
                for stream_kind, line in assembler.flush():
                    ts, msg = self._parse_ts_line(line)
                    size = len(msg.encode("utf-8", "replace"))
                    if rate.allow(size):
                        batch.append({
                            "ts": ts or timezone.now(),
                            "stream": stream_kind,
                            "message": msg,
                        })
                    else:
                        bump_drop(service.pk, entries=1, bytes_dropped=size)
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
                    close_stream(stream, status=ServiceLogStream.Status.CLOSED, owner_id=instance)
            except Exception:
                close_stream(stream, status=ServiceLogStream.Status.LOST, owner_id=instance)

    def _catch_up(self, container, stream, service, policy, instance, rate: RateWindow):
        from logs.usage import bump_drop

        try:
            raw = container.logs(
                stdout=True, stderr=True, timestamps=True, tail=1000
            )
        except Exception as exc:
            logger.warning("catch-up failed %s: %s", container.name, exc)
            return
        pairs = (
            self._demux_docker_chunk(raw)
            if isinstance(raw, (bytes, bytearray))
            else [("stdout", str(raw or ""))]
        )
        lines = []
        skew = stream.last_persisted_ts - timedelta(seconds=5) if stream.last_persisted_ts else None
        for stream_kind, line in pairs:
            if not line:
                continue
            ts, msg = self._parse_ts_line(line)
            if skew and ts and ts < skew:
                continue
            size = len(msg.encode("utf-8", "replace"))
            if not rate.allow(size):
                bump_drop(service.pk, entries=1, bytes_dropped=size)
                continue
            lines.append({
                "ts": ts or timezone.now(),
                "stream": stream_kind,
                "message": msg,
            })
        if lines:
            self._persist_batch(instance, service, stream, policy, lines)

    def _persist_batch(self, instance, service, stream, policy, lines: list):
        from logs.ingestion import ingest_lines
        from logs.realtime import publish_log_events
        from logs.query import encode_cursor
        from django.utils import timezone

        try:
            result = ingest_lines(stream, lines, policy=policy, owner_id=instance)
        except Exception:
            logger.warning("persist failed, buffering", exc_info=True)
            self._buffer.push(service.pk, stream.pk, lines)
            return

        if not policy.realtime_enabled:
            return

        # If persistence is disabled, ingestion still sanitizes the lines before
        # returning them. Never fan out raw Docker output.
        # A stale collector must also stop publishing once its lease expires.
        if result.get("persisted") is False:
            owner = getattr(stream, "owner_id", instance)
            lease_until = getattr(stream, "lease_until", None)
            if owner and owner != instance:
                return
            if lease_until is not None and lease_until <= timezone.now():
                return

        events = []
        for item in result.get("inserted_entries") or []:
            ts = item.get("ts")
            entry_id = item.get("id")
            seq = item.get("seq")
            if ts is None or entry_id is None or seq is None:
                continue
            events.append({
                "id": entry_id,
                "stream_id": stream.pk,
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

        # Non-persistent modes have no durable cursor/sequence. Delivery remains
        # realtime-only and the client is told explicitly that it is ephemeral.
        if not events:
            for item in result.get("realtime_lines") or []:
                ts = item.get("ts")
                events.append({
                    "id": None,
                    "stream_id": stream.pk,
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
            publish_log_events(service.pk, events)

        if result.get("inserted"):
            try:
                from django.conf import settings
                from logs.models import CollectorHeartbeat

                alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
                CollectorHeartbeat.objects.using(alias).filter(instance_id=instance).update(
                    last_successful_ingestion=timezone.now()
                )
            except Exception:
                pass


    def _demux_docker_payloads(self, raw: bytes):
        """Return decoded stdout/stderr payload chunks without line-splitting."""
        if not raw:
            return []
        out = []
        if (
            len(raw) >= 8
            and raw[0] in (1, 2)
            and raw[1:4] == b"\x00\x00\x00"
        ):
            i = 0
            while i + 8 <= len(raw):
                stream_type = raw[i]
                size = int.from_bytes(raw[i + 4 : i + 8], "big")
                i += 8
                if size < 0 or i + size > len(raw):
                    # Defensive fallback for an incomplete/malformed frame.
                    payload = raw[i:]
                    i = len(raw)
                else:
                    payload = raw[i : i + size]
                    i += size
                kind = "stderr" if stream_type == 2 else "stdout"
                out.append((kind, payload.decode("utf-8", "replace")))
            return out
        return [("stdout", raw.decode("utf-8", "replace"))]

    def _demux_docker_chunk(self, raw: bytes):
        """Compatibility helper returning complete lines for catch-up/tests."""
        out = []
        for kind, payload in self._demux_docker_payloads(raw):
            for line in payload.splitlines():
                if line:
                    out.append((kind, line))
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
