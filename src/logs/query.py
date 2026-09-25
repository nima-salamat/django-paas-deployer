"""Historical runtime log queries with cursor pagination."""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from .exceptions import ExpiredCursorError, ExportLimitExceeded
from .models import ServiceLogEntry


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def encode_cursor(
    ts: datetime,
    seq: int,
    *,
    entry_id: int | None = None,
) -> str:
    """Encode a cursor with a global tie-breaker across stream instances."""
    payload = {"ts": ts.isoformat(), "seq": int(seq)}
    if entry_id is not None:
        payload["id"] = int(entry_id)
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor_parts(value: str) -> tuple[datetime, int, int | None]:
    pad = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(value + pad)
    data = json.loads(raw.decode())
    ts = parse_datetime(data["ts"])
    if ts is None:
        raise ValueError("invalid cursor ts")
    entry_id = data.get("id")
    return ts, int(data["seq"]), (int(entry_id) if entry_id is not None else None)


def decode_cursor(value: str) -> tuple[datetime, int]:
    """Backward-compatible decoder for callers that only need ts/seq."""
    ts, seq, _ = _decode_cursor_parts(value)
    return ts, seq


def _cursor_filter(qs, cursor_ts, cursor_seq, cursor_id, direction):
    if cursor_id is not None:
        if direction == "older":
            return qs.filter(
                Q(ts__lt=cursor_ts) | Q(ts=cursor_ts, id__lt=cursor_id)
            )
        return qs.filter(
            Q(ts__gt=cursor_ts) | Q(ts=cursor_ts, id__gt=cursor_id)
        )

    if direction == "older":
        return qs.filter(Q(ts__lt=cursor_ts) | Q(ts=cursor_ts, seq__lt=cursor_seq))
    return qs.filter(Q(ts__gt=cursor_ts) | Q(ts=cursor_ts, seq__gt=cursor_seq))


def query_logs(
    service_id: UUID | str,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    level: str = "",
    stream: str = "",
    q: str = "",
    cursor: str | None = None,
    direction: str = "older",
    limit: int = 100,
) -> dict[str, Any]:
    alias = _alias()
    limit = max(1, min(int(limit or 100), 500))
    qs = ServiceLogEntry.objects.using(alias).filter(service_id=str(service_id))
    if from_ts:
        qs = qs.filter(ts__gte=from_ts)
    if to_ts:
        qs = qs.filter(ts__lte=to_ts)
    if level:
        qs = qs.filter(level__iexact=level)
    if stream in {"stdout", "stderr"}:
        qs = qs.filter(stream=stream)
    if q:
        qs = qs.filter(Q(message__icontains=q))

    cursor_ts = cursor_seq = cursor_id = None
    if cursor:
        try:
            cursor_ts, cursor_seq, cursor_id = _decode_cursor_parts(cursor)
        except Exception as exc:
            raise ValueError("invalid cursor") from exc

        exists_near = (
            qs.filter(pk=cursor_id).exists()
            if cursor_id is not None
            else qs.filter(ts=cursor_ts, seq=cursor_seq).exists()
        )
        candidate_qs = _cursor_filter(
            qs, cursor_ts, cursor_seq, cursor_id, direction
        )
        if not exists_near and not candidate_qs.exists() and qs.exists():
            raise ExpiredCursorError("cursor expired or no data in requested direction")

        qs = candidate_qs
        if direction == "older":
            rows = list(qs.order_by("-ts", "-id")[: limit + 1])
            has_more = len(rows) > limit
            rows = rows[:limit]
            rows.reverse()
        else:
            rows = list(qs.order_by("ts", "id")[: limit + 1])
            has_more = len(rows) > limit
            rows = rows[:limit]
    else:
        rows_desc = list(qs.order_by("-ts", "-id")[: limit + 1])
        has_more = len(rows_desc) > limit
        rows = list(reversed(rows_desc[:limit]))

    events = [
        {
            "id": r.id,
            "stream_id": r.stream_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "seq": r.seq,
            "stream": r.stream,
            "level": r.level or None,
            "message": r.message,
            "byte_size": r.byte_size,
            "truncated": r.truncated,
            "cursor": encode_cursor(r.ts, r.seq, entry_id=r.id) if r.ts else None,
        }
        for r in rows
    ]
    next_cursor = None
    prev_cursor = None
    if rows:
        next_cursor = encode_cursor(rows[0].ts, rows[0].seq, entry_id=rows[0].id)
        prev_cursor = encode_cursor(rows[-1].ts, rows[-1].seq, entry_id=rows[-1].id)
    return {
        "events": events,
        "has_more_older": has_more if direction == "older" or not cursor else has_more,
        "has_more_newer": has_more if direction == "newer" else False,
        "next_cursor": next_cursor,
        "prev_cursor": prev_cursor,
        "count": len(events),
    }


EXPORT_MAX_ROWS = 10_000


def export_logs(service_id: UUID | str, *, fmt: str = "txt", **filters) -> tuple[str, str]:
    """Return (content_type, body). Bounded export."""
    limit = min(int(filters.pop("limit", EXPORT_MAX_ROWS) or EXPORT_MAX_ROWS), EXPORT_MAX_ROWS)
    data = query_logs(service_id, limit=limit, **filters)
    events = data["events"]
    if fmt == "jsonl":
        lines = [json.dumps(e, ensure_ascii=False) for e in events]
        return "application/x-ndjson; charset=utf-8", "\n".join(lines) + ("\n" if lines else "")
    # txt
    out = []
    for e in events:
        out.append(f"{e.get('ts') or ''} [{e.get('stream')}] {e.get('message') or ''}")
    return "text/plain; charset=utf-8", "\n".join(out) + ("\n" if out else "")
