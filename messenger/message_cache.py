"""
Messenger hot-cache (Redis).

Scope
-----
* Messages: sliding window of the latest MESSAGE_CACHE_SIZE messages
  **per conversation** (not per user).  Keys:
      msgcache:{conversation_id}:ids
      msgcache:{conversation_id}:m:{msg_id}
      msgcache:{conversation_id}:meta
* Conversation list: short-lived JSON **per user**
      msgcache:user:{user_id}:conv_list
* Participants of a conversation:
      msgcache:{conversation_id}:participants

PostgreSQL is always the source of truth.  Redis is never written before a
successful DB commit.  Cache updates are scheduled with
``transaction.on_commit`` so the HTTP response is not blocked by Redis.

Viewer-specific fields (reactions.mine, read_state, unread_count) are either
recomputed per request or stored only in short-TTL user-scoped keys.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

_PREFIX = "msgcache"


def _ids_key(conv_id: int) -> str:
    return f"{_PREFIX}:{conv_id}:ids"


def _msg_key(conv_id: int, msg_id: int) -> str:
    return f"{_PREFIX}:{conv_id}:m:{msg_id}"


def _meta_key(conv_id: int) -> str:
    return f"{_PREFIX}:{conv_id}:meta"


def _cache_size() -> int:
    return int(getattr(settings, "MESSAGE_CACHE_SIZE", 1000) or 1000)


def _cache_ttl() -> int:
    """0 means no expiry."""
    return int(getattr(settings, "MESSAGE_CACHE_TTL", 6 * 3600) or 0)


# ---------------------------------------------------------------------------
# Redis client
# ---------------------------------------------------------------------------

def _redis():
    """Return the raw redis-py client from django-redis (db/2)."""
    try:
        from django_redis import get_redis_connection
        return get_redis_connection("default")
    except Exception:
        logger.exception("message_cache: cannot obtain redis connection")
        return None


STATS_KEY = f"{_PREFIX}:stats"


def _incr_stat(field: str, amount: int = 1) -> None:
    r = _redis()
    if not r:
        return
    try:
        r.hincrby(STATS_KEY, field, amount)
    except Exception:
        pass


def record_hit(kind: str = "msg") -> None:
    _incr_stat(f"{kind}_hit")


def record_miss(kind: str = "msg") -> None:
    _incr_stat(f"{kind}_miss")


def get_cache_stats() -> dict:
    """Return hit/miss counters and basic redis info for admin UI."""
    r = _redis()
    out = {
        "redis_ok": False,
        "msg_hit": 0,
        "msg_miss": 0,
        "list_hit": 0,
        "list_miss": 0,
        "cached_conversations": 0,
        "message_cache_size": _cache_size(),
        "message_cache_ttl": _cache_ttl(),
        "redis_info": {},
    }
    if not r:
        return out
    try:
        out["redis_ok"] = bool(r.ping())
        raw = r.hgetall(STATS_KEY) or {}
        def _i(k):
            v = raw.get(k) or raw.get(k.encode() if isinstance(k, str) else k)
            if v is None:
                return 0
            if isinstance(v, bytes):
                v = v.decode()
            return int(v)
        out["msg_hit"] = _i("msg_hit")
        out["msg_miss"] = _i("msg_miss")
        out["list_hit"] = _i("list_hit")
        out["list_miss"] = _i("list_miss")
        # count meta keys
        try:
            # SCAN msgcache:*:meta
            n = 0
            for key in r.scan_iter(match=f"{_PREFIX}:*:meta", count=200):
                n += 1
                if n >= 5000:
                    break
            out["cached_conversations"] = n
        except Exception:
            pass
        try:
            info = r.info(section="memory")
            out["redis_info"] = {
                "used_memory_human": info.get("used_memory_human"),
                "maxmemory_human": info.get("maxmemory_human"),
            }
        except Exception:
            pass
    except Exception:
        logger.exception("get_cache_stats failed")
    return out


def inspect_conversation_cache(conv_id: int) -> dict:
    """Detailed view of one conversation's hot window for admin."""
    r = _redis()
    result = {
        "conversation_id": conv_id,
        "redis_ok": bool(r),
        "meta": None,
        "message_ids": [],
        "messages": [],
        "ids_key": _ids_key(conv_id),
        "meta_key": _meta_key(conv_id),
    }
    if not r:
        return result
    try:
        result["meta"] = MessageCacheService.get_meta(conv_id)
        raw_ids = r.zrange(_ids_key(conv_id), 0, -1)
        ids = []
        for x in raw_ids:
            if isinstance(x, bytes):
                x = x.decode()
            ids.append(int(x))
        result["message_ids"] = ids
        pipe = r.pipeline(transaction=False)
        for mid in ids[-50:]:  # last 50 for UI
            pipe.get(_msg_key(conv_id, mid))
        payloads = pipe.execute()
        for mid, raw in zip(ids[-50:], payloads):
            data = _json_loads(raw)
            if data:
                result["messages"].append({
                    "id": data.get("id"),
                    "body": (data.get("body") or "")[:120],
                    "sender": data.get("sender"),
                    "is_edited": data.get("is_edited"),
                    "is_deleted": data.get("is_deleted"),
                    "created_at": data.get("created_at"),
                    "reactions_agg": data.get("reactions_agg"),
                })
    except Exception:
        logger.exception("inspect_conversation_cache failed")
    return result


def search_cache_keys(pattern: str = "msgcache:*", limit: int = 100) -> list:
    r = _redis()
    if not r:
        return []
    out = []
    try:
        for key in r.scan_iter(match=pattern, count=200):
            k = key.decode() if isinstance(key, bytes) else str(key)
            try:
                ktype = r.type(key)
                if isinstance(ktype, bytes):
                    ktype = ktype.decode()
                ttl = r.ttl(key)
            except Exception:
                ktype, ttl = "?", -1
            out.append({"key": k, "type": ktype, "ttl": ttl})
            if len(out) >= limit:
                break
    except Exception:
        logger.exception("search_cache_keys failed")
    return out


def reset_cache_stats() -> None:
    r = _redis()
    if not r:
        return
    try:
        r.delete(STATS_KEY)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Serialization helpers (base payload – no viewer-specific data)
# ---------------------------------------------------------------------------

def _dt(val) -> Optional[str]:
    if val is None:
        return None
    if timezone.is_naive(val):
        val = timezone.make_aware(val, timezone.get_current_timezone())
    return val.isoformat()


def _user_mini(user) -> Optional[Dict[str, Any]]:
    if user is None:
        return None
    # Keep the same shape UserMiniSerializer produces for list views.
    # Avatar URL resolution is left to the live serializer when possible;
    # we store the raw fields so the cache stays self-contained.
    avatar = getattr(user, "avatar", None)
    avatar_url = None
    if avatar:
        try:
            avatar_url = avatar.url
        except Exception:
            avatar_url = None
    return {
        "id": user.id,
        "username": getattr(user, "username", None) or "",
        "first_name": getattr(user, "first_name", None) or "",
        "last_name": getattr(user, "last_name", None) or "",
        "avatar": avatar_url,
    }


def _attachment_dict(att) -> Dict[str, Any]:
    url = None
    try:
        url = att.file.url if att.file else None
    except Exception:
        url = None
    return {
        "id": att.id,
        "original_filename": att.original_filename,
        "content_type": att.content_type,
        "size": att.size,
        "kind": att.kind,
        "width": att.width,
        "height": att.height,
        "duration": att.duration,
        "url": url,
        "created_at": _dt(att.created_at),
    }


def message_to_cache_dict(msg) -> Dict[str, Any]:
    """Build a JSON-serialisable base payload for one Message instance.

    Must be called with a Message that already has select_related /
    prefetch_related applied for sender, reply_to, reply_to__sender,
    forwarded_from, attachments.
    """
    reply_preview = None
    if msg.reply_to_id:
        r = getattr(msg, "reply_to", None)
        if not r or getattr(r, "is_deleted", False):
            reply_preview = {"id": msg.reply_to_id, "body": "Deleted message", "sender": None}
        else:
            reply_preview = {
                "id": r.id,
                "body": (r.body or "")[:120],
                "sender": _user_mini(getattr(r, "sender", None)),
            }

    # Aggregate reactions as {emoji: count} – "mine" is filled per-request.
    reactions_agg: Dict[str, int] = {}
    try:
        reactions = list(msg.reactions.all())
    except Exception:
        reactions = []
    for r in reactions:
        reactions_agg[r.emoji] = reactions_agg.get(r.emoji, 0) + 1

    attachments = []
    try:
        attachments = [_attachment_dict(a) for a in msg.attachments.all()]
    except Exception:
        pass

    return {
        "id": msg.id,
        "conversation": msg.conversation_id,
        "sender": _user_mini(getattr(msg, "sender", None)),
        "body": msg.body or "",
        "reply_to": msg.reply_to_id,
        "reply_to_preview": reply_preview,
        "forwarded_from": msg.forwarded_from_id,
        "forwarded_from_user": _user_mini(getattr(msg, "forwarded_from", None)),
        "forwarded_from_message": msg.forwarded_from_message_id,
        "is_edited": bool(msg.is_edited),
        "is_system": bool(msg.is_system),
        "is_deleted": bool(msg.is_deleted),
        "created_at": _dt(msg.created_at),
        "updated_at": _dt(msg.updated_at),
        "attachments": attachments,
        "reactions_agg": reactions_agg,  # {emoji: count}
        "scheduled_for": _dt(getattr(msg, "scheduled_for", None)),
        "is_scheduled": bool(getattr(msg, "is_scheduled", False)),
    }


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _json_loads(raw: Any) -> Optional[Dict]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# MessageCacheService
# ---------------------------------------------------------------------------

class MessageCacheService:
    """Shared Redis hot-cache for the latest messages of a conversation."""

    # ------------------------------------------------------------------
    # Meta / range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_meta(conv_id: int) -> Optional[Dict[str, int]]:
        r = _redis()
        if not r:
            return None
        try:
            raw = r.hgetall(_meta_key(conv_id))
            if not raw:
                return None
            # redis-py may return bytes keys/values
            def _g(k):
                v = raw.get(k) or raw.get(k.encode())
                if v is None:
                    return None
                if isinstance(v, bytes):
                    v = v.decode()
                return int(v)

            return {
                "min_id": _g("min_id"),
                "max_id": _g("max_id"),
                "count": _g("count") or 0,
            }
        except Exception:
            logger.exception("message_cache.get_meta failed conv=%s", conv_id)
            return None

    @staticmethod
    def is_range_cached(
        conv_id: int,
        before_id: Optional[int],
        limit: int,
    ) -> bool:
        """Return True when the requested window is fully covered by cache.

        The cache always holds a contiguous suffix of the latest messages
        (by id).  Therefore:

        * no before_id  → latest page is cached iff meta exists and count > 0
        * before_id = X → cached iff X > min_id  (there is at least one
          message with id < X still inside the window)
        """
        meta = MessageCacheService.get_meta(conv_id)
        if not meta or meta["count"] <= 0 or meta["min_id"] is None:
            return False
        if before_id is None:
            return True
        # Need messages with id < before_id.  Possible only if min_id < before_id.
        return meta["min_id"] < int(before_id)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    @staticmethod
    def get_cached_messages(
        conv_id: int,
        before_id: Optional[int],
        limit: int,
    ) -> Optional[Tuple[List[Dict], bool, Optional[int]]]:
        """
        Return (messages_asc, has_more, next_before_id) or None on miss/error.

        messages_asc is a list of base cache dicts ordered oldest → newest
        (same order the API returns after the final reverse).
        """
        r = _redis()
        if not r:
            return None
        if not MessageCacheService.is_range_cached(conv_id, before_id, limit):
            record_miss("msg")
            return None

        try:
            ids_key = _ids_key(conv_id)
            # ZREVRANGEBYSCORE: highest scores first (newest first)
            max_score = (int(before_id) - 1) if before_id else "+inf"
            # Fetch limit+1 to detect has_more
            raw_ids = r.zrevrangebyscore(
                ids_key, max_score, "-inf", start=0, num=limit + 1
            )
            if not raw_ids:
                return None

            has_more = len(raw_ids) > limit
            raw_ids = raw_ids[:limit]
            # Convert to ints, keep newest→oldest then reverse later
            msg_ids = []
            for x in raw_ids:
                if isinstance(x, bytes):
                    x = x.decode()
                msg_ids.append(int(x))

            # Pipeline GET for all message payloads
            pipe = r.pipeline(transaction=False)
            for mid in msg_ids:
                pipe.get(_msg_key(conv_id, mid))
            payloads = pipe.execute()

            messages: List[Dict] = []
            for mid, raw in zip(msg_ids, payloads):
                data = _json_loads(raw)
                if data is None:
                    # Incomplete cache → treat as miss so we rebuild
                    logger.warning(
                        "message_cache: missing payload for msg %s in conv %s",
                        mid, conv_id,
                    )
                    return None
                messages.append(data)

            # messages is newest→oldest; API returns oldest→newest
            messages.reverse()
            next_before = messages[0]["id"] if has_more and messages else None
            record_hit("msg")
            return messages, has_more, next_before
        except Exception:
            logger.exception("message_cache.get_cached_messages failed conv=%s", conv_id)
            return None

    # ------------------------------------------------------------------
    # Write path – populate / rebuild
    # ------------------------------------------------------------------

    @staticmethod
    def cache_messages(conv_id: int, messages: Sequence) -> None:
        """Replace the cache window for a conversation with the given messages.

        `messages` should be the latest MESSAGE_CACHE_SIZE messages ordered
        oldest → newest (or any order – we sort by id).
        """
        r = _redis()
        if not r or not messages:
            return
        size = _cache_size()
        ttl = _cache_ttl()
        try:
            # Keep only the newest `size` by id
            sorted_msgs = sorted(messages, key=lambda m: m.id)[-size:]
            ids_key = _ids_key(conv_id)
            meta_key = _meta_key(conv_id)

            pipe = r.pipeline(transaction=True)
            # Clear old window
            pipe.delete(ids_key)
            # We intentionally leave orphan msg keys; they expire via TTL
            # or are overwritten.  Cleaning them all would need a SCAN.

            for msg in sorted_msgs:
                payload = message_to_cache_dict(msg)
                mid = msg.id
                pipe.set(_msg_key(conv_id, mid), _json_dumps(payload))
                pipe.zadd(ids_key, {str(mid): mid})
                if ttl > 0:
                    pipe.expire(_msg_key(conv_id, mid), ttl)

            min_id = sorted_msgs[0].id
            max_id = sorted_msgs[-1].id
            pipe.hset(
                meta_key,
                mapping={
                    "min_id": min_id,
                    "max_id": max_id,
                    "count": len(sorted_msgs),
                },
            )
            if ttl > 0:
                pipe.expire(ids_key, ttl)
                pipe.expire(meta_key, ttl)
            pipe.execute()
        except Exception:
            logger.exception("message_cache.cache_messages failed conv=%s", conv_id)

    @staticmethod
    def rebuild_chat_cache(conv_id: int) -> None:
        """Reload the latest MESSAGE_CACHE_SIZE messages from Postgres."""
        from .models import Message

        size = _cache_size()
        try:
            qs = (
                Message.objects.filter(conversation_id=conv_id, is_deleted=False)
                .filter(is_scheduled=False)
                .select_related(
                    "sender", "reply_to", "reply_to__sender", "forwarded_from"
                )
                .prefetch_related("attachments", "reactions")
                .order_by("-id")[:size]
            )
            msgs = list(qs)
            msgs.reverse()  # oldest → newest
            MessageCacheService.cache_messages(conv_id, msgs)
        except Exception:
            logger.exception("message_cache.rebuild_chat_cache failed conv=%s", conv_id)

    # ------------------------------------------------------------------
    # Incremental updates (after successful DB commit)
    # ------------------------------------------------------------------

    @staticmethod
    def add_message(msg) -> None:
        """Insert a newly created message into the hot window (sliding)."""
        r = _redis()
        if not r:
            return
        conv_id = msg.conversation_id
        size = _cache_size()
        ttl = _cache_ttl()
        try:
            # Ensure we have the full payload relations
            if not hasattr(msg, "_prefetched_objects_cache"):
                from .models import Message
                msg = (
                    Message.objects.filter(pk=msg.pk)
                    .select_related(
                        "sender", "reply_to", "reply_to__sender", "forwarded_from"
                    )
                    .prefetch_related("attachments", "reactions")
                    .first()
                )
                if not msg:
                    return

            payload = message_to_cache_dict(msg)
            mid = msg.id
            ids_key = _ids_key(conv_id)
            meta_key = _meta_key(conv_id)
            msg_key = _msg_key(conv_id, mid)

            pipe = r.pipeline(transaction=True)
            pipe.set(msg_key, _json_dumps(payload))
            pipe.zadd(ids_key, {str(mid): mid})
            # Trim to size (remove oldest)
            pipe.zremrangebyrank(ids_key, 0, -(size + 1))
            if ttl > 0:
                pipe.expire(msg_key, ttl)
                pipe.expire(ids_key, ttl)

            # Refresh meta from the ZSET
            pipe.zrange(ids_key, 0, 0)          # min
            pipe.zrange(ids_key, -1, -1)        # max
            pipe.zcard(ids_key)
            results = pipe.execute()
            # results indices: set, zadd, zrem..., [expire...], zrange_min, zrange_max, zcard
            # Because of optional expires the offsets vary; re-fetch cleanly.
            min_raw = r.zrange(ids_key, 0, 0)
            max_raw = r.zrange(ids_key, -1, -1)
            count = r.zcard(ids_key)
            min_id = int(min_raw[0]) if min_raw else mid
            max_id = int(max_raw[0]) if max_raw else mid
            r.hset(
                meta_key,
                mapping={"min_id": min_id, "max_id": max_id, "count": count},
            )
            if ttl > 0:
                r.expire(meta_key, ttl)
        except Exception:
            logger.exception("message_cache.add_message failed msg=%s", getattr(msg, "id", None))

    @staticmethod
    def update_message(msg) -> None:
        """Refresh a single message payload if it lives in the cache."""
        r = _redis()
        if not r:
            return
        conv_id = msg.conversation_id
        mid = msg.id
        try:
            # Only update if the id is present in the window
            if r.zscore(_ids_key(conv_id), str(mid)) is None:
                return

            from .models import Message
            fresh = (
                Message.objects.filter(pk=mid)
                .select_related(
                    "sender", "reply_to", "reply_to__sender", "forwarded_from"
                )
                .prefetch_related("attachments", "reactions")
                .first()
            )
            if not fresh:
                return
            payload = message_to_cache_dict(fresh)
            ttl = _cache_ttl()
            key = _msg_key(conv_id, mid)
            r.set(key, _json_dumps(payload))
            if ttl > 0:
                r.expire(key, ttl)
        except Exception:
            logger.exception("message_cache.update_message failed msg=%s", mid)

    @staticmethod
    def delete_message(conv_id: int, msg_id: int) -> None:
        """Remove a message from the hot window (soft-delete or hard remove)."""
        r = _redis()
        if not r:
            return
        try:
            ids_key = _ids_key(conv_id)
            msg_key = _msg_key(conv_id, msg_id)
            meta_key = _meta_key(conv_id)

            pipe = r.pipeline(transaction=True)
            pipe.zrem(ids_key, str(msg_id))
            pipe.delete(msg_key)
            pipe.execute()

            # Refresh meta
            min_raw = r.zrange(ids_key, 0, 0)
            max_raw = r.zrange(ids_key, -1, -1)
            count = r.zcard(ids_key)
            if count == 0:
                r.delete(meta_key)
            else:
                min_id = int(min_raw[0]) if min_raw else 0
                max_id = int(max_raw[0]) if max_raw else 0
                r.hset(
                    meta_key,
                    mapping={"min_id": min_id, "max_id": max_id, "count": count},
                )
        except Exception:
            logger.exception(
                "message_cache.delete_message failed conv=%s msg=%s", conv_id, msg_id
            )

    @staticmethod
    def invalidate_chat_cache(conv_id: int) -> None:
        """Drop the entire window (e.g. after major history changes)."""
        r = _redis()
        if not r:
            return
        try:
            ids_key = _ids_key(conv_id)
            meta_key = _meta_key(conv_id)
            # Delete known message keys
            members = r.zrange(ids_key, 0, -1)
            pipe = r.pipeline(transaction=False)
            for m in members:
                mid = int(m.decode() if isinstance(m, bytes) else m)
                pipe.delete(_msg_key(conv_id, mid))
            pipe.delete(ids_key)
            pipe.delete(meta_key)
            pipe.execute()
        except Exception:
            logger.exception("message_cache.invalidate_chat_cache failed conv=%s", conv_id)

    # ------------------------------------------------------------------
    # Response enrichment (viewer-specific fields)
    # ------------------------------------------------------------------

    @staticmethod
    def enrich_for_viewer(
        base_messages: List[Dict],
        request,
        conversation_id: int,
    ) -> List[Dict]:
        """Turn base cache dicts into full API-compatible payloads.

        Uses reactions_agg from cache for counts; only one small query for
        the viewer's own reactions (mine) and read receipts.
        """
        from .models import MessageReaction, MessageReadReceipt, ConversationParticipant

        if not base_messages:
            return []

        viewer = getattr(request, "user", None) if request else None
        viewer_id = getattr(viewer, "id", None) if viewer and getattr(viewer, "is_authenticated", False) else None
        msg_ids = [m["id"] for m in base_messages]

        # mine flags only (counts come from cache)
        mine_map: Dict[int, set] = {mid: set() for mid in msg_ids}
        if viewer_id and msg_ids:
            for row in (
                MessageReaction.objects.filter(message_id__in=msg_ids, user_id=viewer_id)
                .values("message_id", "emoji")
            ):
                mine_map[row["message_id"]].add(row["emoji"])

        # read_state for viewer's own messages
        own_ids = [
            m["id"]
            for m in base_messages
            if m.get("sender") and m["sender"].get("id") == viewer_id
        ]
        read_ids = set()
        if own_ids and viewer_id:
            read_ids = set(
                MessageReadReceipt.objects.filter(message_id__in=own_ids)
                .exclude(user_id=viewer_id)
                .values_list("message_id", flat=True)
                .distinct()
            )
            others = list(
                ConversationParticipant.objects.filter(
                    conversation_id=conversation_id, left_at__isnull=True
                )
                .exclude(user_id=viewer_id)
                .values_list("user_id", "last_read_at")
            )
            for m in base_messages:
                if m["id"] in read_ids:
                    continue
                if not m.get("sender") or m["sender"].get("id") != viewer_id:
                    continue
                created = m.get("created_at")
                if not created:
                    continue
                from django.utils.dateparse import parse_datetime
                created_dt = parse_datetime(created) if isinstance(created, str) else created
                if created_dt is None:
                    continue
                for _uid, lr in others:
                    if lr and lr >= created_dt:
                        read_ids.add(m["id"])
                        break

        result = []
        for m in base_messages:
            out = dict(m)
            mid = out["id"]
            agg = out.get("reactions_agg") or {}
            mine = mine_map.get(mid) or set()
            out["reactions"] = [
                {"emoji": em, "count": int(cnt), "mine": em in mine}
                for em, cnt in sorted(agg.items())
            ]
            out.pop("reactions_agg", None)

            if out.get("is_system") or out.get("is_deleted"):
                out["read_state"] = "read"
            elif not viewer_id or not out.get("sender") or out["sender"].get("id") != viewer_id:
                out["read_state"] = "read"
            else:
                out["read_state"] = "read" if mid in read_ids else "sent"

            result.append(out)
        return result


# ===========================================================================
# Non-blocking scheduling: never block the API response on Redis I/O
# ===========================================================================

def run_after_commit(fn, *args, **kwargs):
    """Run ``fn(*args, **kwargs)`` after the current DB transaction commits.

    If there is no open transaction, runs immediately.  Exceptions inside
    ``fn`` are logged and never propagated to the caller.
    """
    from django.db import transaction

    def _safe():
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("run_after_commit: %s failed", getattr(fn, "__name__", fn))

    try:
        transaction.on_commit(_safe)
    except Exception:
        # No connection / outside atomic block
        _safe()


# ===========================================================================
# Conversation-level caches (list per user, participants per chat)
# ===========================================================================

def _user_list_key(user_id: int) -> str:
    return f"{_PREFIX}:user:{user_id}:conv_list"


def _participants_key(conv_id: int) -> str:
    return f"{_PREFIX}:{conv_id}:participants"


def _list_ttl() -> int:
    return int(getattr(settings, "MESSENGER_LIST_CACHE_TTL", 60) or 60)


def _conv_ttl() -> int:
    return int(getattr(settings, "MESSENGER_CONV_CACHE_TTL", 120) or 120)


class ConversationCacheService:
    """Short-lived caches for conversation list and participants.

    Conversation list is **per user** (pin state, unread, ordering differ).
    Participants are **per conversation** (shared across members).
    """

    # ----- conversation list (per user) -----

    @staticmethod
    def get_user_conv_list(user_id: int) -> Optional[List[Dict]]:
        r = _redis()
        if not r:
            return None
        try:
            raw = r.get(_user_list_key(user_id))
            data = _json_loads(raw)
            if data is None:
                record_miss("list")
            else:
                record_hit("list")
            return data
        except Exception:
            logger.exception("get_user_conv_list failed user=%s", user_id)
            return None

    @staticmethod
    def set_user_conv_list(user_id: int, payload: List[Dict]) -> None:
        r = _redis()
        if not r:
            return
        try:
            ttl = _list_ttl()
            key = _user_list_key(user_id)
            r.set(key, _json_dumps(payload))
            if ttl > 0:
                r.expire(key, ttl)
        except Exception:
            logger.exception("set_user_conv_list failed user=%s", user_id)

    @staticmethod
    def invalidate_user_conv_list(user_id: int) -> None:
        r = _redis()
        if not r:
            return
        try:
            r.delete(_user_list_key(user_id))
        except Exception:
            logger.exception("invalidate_user_conv_list failed user=%s", user_id)

    @staticmethod
    def invalidate_conv_lists_for_conversation(conv_id: int) -> None:
        """Drop list cache for every active participant of a conversation.

        Called after new message / member change so the next list fetch is fresh.
        """
        r = _redis()
        if not r:
            return
        try:
            from .models import ConversationParticipant
            uids = list(
                ConversationParticipant.objects.filter(
                    conversation_id=conv_id, left_at__isnull=True
                ).values_list("user_id", flat=True)
            )
            if not uids:
                return
            pipe = r.pipeline(transaction=False)
            for uid in uids:
                pipe.delete(_user_list_key(uid))
            pipe.execute()
        except Exception:
            logger.exception(
                "invalidate_conv_lists_for_conversation failed conv=%s", conv_id
            )

    # ----- participants (per conversation) -----

    @staticmethod
    def get_participants(conv_id: int) -> Optional[List[Dict]]:
        r = _redis()
        if not r:
            return None
        try:
            raw = r.get(_participants_key(conv_id))
            return _json_loads(raw)
        except Exception:
            logger.exception("get_participants failed conv=%s", conv_id)
            return None

    @staticmethod
    def set_participants(conv_id: int, payload: List[Dict]) -> None:
        r = _redis()
        if not r:
            return
        try:
            ttl = _conv_ttl()
            key = _participants_key(conv_id)
            r.set(key, _json_dumps(payload))
            if ttl > 0:
                r.expire(key, ttl)
        except Exception:
            logger.exception("set_participants failed conv=%s", conv_id)

    @staticmethod
    def invalidate_participants(conv_id: int) -> None:
        r = _redis()
        if not r:
            return
        try:
            r.delete(_participants_key(conv_id))
        except Exception:
            logger.exception("invalidate_participants failed conv=%s", conv_id)


# ===========================================================================
# Convenience: schedule message-cache mutations after DB commit
# ===========================================================================

def schedule_add_message(msg) -> None:
    """After commit: add message to hot window + invalidate affected lists."""
    conv_id = getattr(msg, "conversation_id", None) or (
        msg.conversation.id if getattr(msg, "conversation", None) else None
    )
    msg_id = getattr(msg, "id", None)

    def _job():
        from .models import Message
        fresh = (
            Message.objects.filter(pk=msg_id)
            .select_related(
                "sender", "reply_to", "reply_to__sender", "forwarded_from"
            )
            .prefetch_related("attachments", "reactions")
            .first()
        )
        if fresh:
            MessageCacheService.add_message(fresh)
        if conv_id:
            ConversationCacheService.invalidate_conv_lists_for_conversation(conv_id)

    run_after_commit(_job)


def schedule_update_message(msg) -> None:
    msg_id = getattr(msg, "id", None)
    conv_id = getattr(msg, "conversation_id", None)

    def _job():
        from .models import Message
        fresh = Message.objects.filter(pk=msg_id).first()
        if fresh:
            MessageCacheService.update_message(fresh)
        if conv_id:
            ConversationCacheService.invalidate_conv_lists_for_conversation(conv_id)

    run_after_commit(_job)


def schedule_delete_message(conv_id: int, msg_id: int) -> None:
    def _job():
        MessageCacheService.delete_message(conv_id, msg_id)
        ConversationCacheService.invalidate_conv_lists_for_conversation(conv_id)

    run_after_commit(_job)
