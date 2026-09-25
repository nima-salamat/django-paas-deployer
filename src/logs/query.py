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


def encode_cursor(ts: datetime, seq: int) -> str:
    payload = json.dumps({"ts": ts.isoformat(), "seq": int(seq)})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, int]:
    pad = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(value + pad)
    data = json.loads(raw.decode())
    ts = parse_datetime(data["ts"])
    if ts is None:
        raise ValueError("invalid cursor ts")
    return ts, int(data["seq"])


def query_logs(
    service_id: UUID | str,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    level: str = "",
    stream: str = "",
    q: str = "",
    cursor: str | None = None,
    direction: str = "older",  # older = before cursor (default history), newer = after
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

    cursor_ts = cursor_seq = None
    if cursor:
        try:
            cursor_ts, cursor_seq = decode_cursor(cursor)
        except Exception as exc:
            raise ValueError("invalid cursor") from exc
        # Expired if no rows exist at/near cursor and nothing newer/older in range
        exists_near = qs.filter(ts=cursor_ts, seq=cursor_seq).exists()
        if direction == "older":
            if not exists_near and not qs.filter(ts__lt=cursor_ts).exists() and not qs.filter(ts=cursor_ts, seq__lt=cursor_seq).exists():
                # still allow if there is older data without exact match
                if not qs.filter(Q(ts__lt=cursor_ts) | Q(ts=cursor_ts, seq__lt=cursor_seq)).exists():
                    if not qs.exists():
                        raise ExpiredCursorError("cursor expired or empty history")
            qs = qs.filter(Q(ts__lt=cursor_ts) | Q(ts=cursor_ts, seq__lt=cursor_seq))
            rows = list(qs.order_by("-ts", "-seq")[: limit + 1])
            has_more = len(rows) > limit
            rows = rows[:limit]
            rows.reverse()  # chronological for UI
        else:
            qs = qs.filter(Q(ts__gt=cursor_ts) | Q(ts=cursor_ts, seq__gt=cursor_seq))
            rows = list(qs.order_by("ts", "seq")[: limit + 1])
            has_more = len(rows) > limit
            rows = rows[:limit]
    else:
        # Latest page (oldest of the newest window) when no cursor: last N
        rows_desc = list(qs.order_by("-ts", "-seq")[: limit + 1])
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
            "cursor": encode_cursor(r.ts, r.seq) if r.ts else None,
        }
        for r in rows
    ]
    next_cursor = None
    prev_cursor = None
    if rows:
        next_cursor = encode_cursor(rows[0].ts, rows[0].seq)  # load older
        prev_cursor = encode_cursor(rows[-1].ts, rows[-1].seq)  # load newer
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
