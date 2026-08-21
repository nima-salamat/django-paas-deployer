"""
Messenger hot-cache (Redis).

Architecture (messages)
-----------------------
Per conversation we keep a **contiguous suffix** of the newest
``MESSAGE_CACHE_SIZE`` messages, as two layers:

1. Ordered id index (list of message ids, score = id)::

       msgcache:{conversation_id}:ids          Redis ZSET

2. Message payloads (one key per id)::

       msgcache:{conversation_id}:m:{msg_id}   Redis STRING (JSON)

3. Bounds for O(1) range checks::

       msgcache:{conversation_id}:meta         HASH {min_id, max_id, count}

Reads never walk "page numbers".  A request is a **chunk by id**:

* latest / ``before_id`` → ZREVRANGEBYSCORE then MGET payloads
* ``after_id``           → ZRANGEBYSCORE then MGET
* ``around_id``          → older half + newer half around that id

When the window exceeds ``MESSAGE_CACHE_SIZE``, the oldest ids are trimmed
from the ZSET and their payload keys are deleted (sliding window).

Add / update / delete keep the ZSET and payloads in sync after DB commit
(``transaction.on_commit``).  PostgreSQL remains the source of truth; Redis
is a hot path only.  Ranges outside ``[min_id, max_id]`` fall through to DB.

Also
----
* Conversation list: short-lived JSON **per user**
      msgcache:user:{user_id}:conv_list
* Participants of a conversation:
      msgcache:{conversation_id}:participants

Viewer-specific fields (reactions.mine, read_state, unread_count) are
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
        out["list_set_ok"] = _i("list_set_ok")
        out["list_set_fail"] = _i("list_set_fail")
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


def invalidate_all_cache(reset_stats: bool = False) -> int:
    """Delete every Messenger-owned Redis key safely using SCAN.

    Returns the approximate number of deleted keys. The operation is bounded by
    Redis SCAN and never uses KEYS, so it is suitable for production Redis.
    """
    r = _redis()
    if not r:
        return 0
    deleted = 0
    try:
        pipe = r.pipeline(transaction=False)
        batch = 0
        for key in r.scan_iter(match=f"{_PREFIX}:*", count=500):
            pipe.delete(key)
            batch += 1
            if batch >= 500:
                deleted += int(sum(pipe.execute()) or 0)
                batch = 0
        if batch:
            deleted += int(sum(pipe.execute()) or 0)
        if reset_stats:
            reset_cache_stats()
    except Exception:
        logger.exception("message_cache.invalidate_all_cache failed")
    return deleted


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
    # Avatars live on users.Profile (not User.avatar). Privacy applied in enrich_for_viewer.
    avatar_url = None
    try:
        from users.models import Profile
        p = (
            Profile.objects.filter(user_id=user.id)
            .exclude(image__isnull=True)
            .exclude(image="")
            .order_by("order", "id")
            .only("image")
            .first()
        )
        if p is not None and p.image:
            avatar_url = p.image.url
    except Exception:
        avatar_url = None
    return {
        "id": user.id,
        "username": getattr(user, "username", None) or "",
        "first_name": getattr(user, "first_name", None) or "",
        "last_name": getattr(user, "last_name", None) or "",
        "avatar": avatar_url,
        "color": getattr(user, "color", None),
    }


def _attachment_dict(att) -> Dict[str, Any]:
    is_vo = bool(getattr(att, "is_view_once", False))
    is_purged = bool(getattr(att, "is_purged", False))
    # Never put a durable download URL for view-once in the shared cache;
    # enrich_for_viewer fills viewer-specific fields.
    url = None if (is_vo or is_purged) else f"/api/messenger/attachments/{att.id}/download/"
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
        "is_spoiler": bool(getattr(att, "is_spoiler", False)),
        "is_view_once": is_vo,
        "is_purged": is_purged,
        "view_once_state": "purged" if is_purged else ("pending" if is_vo else "none"),
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
    from django.core.serializers.json import DjangoJSONEncoder
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, cls=DjangoJSONEncoder)


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
        """Return True when a before_id / latest page is fully inside the hot window.

        Cache holds a contiguous **suffix** of the latest messages (by id):
          msgcache:{conv}:ids   → Redis ZSET  member=msg_id, score=msg_id
          msgcache:{conv}:m:{id} → JSON payload per message
          msgcache:{conv}:meta  → min_id / max_id / count

        * no before_id  → latest page is cached iff meta exists and count > 0
        * before_id = X → cached iff min_id < X (at least one older id still in window)
        """
        meta = MessageCacheService.get_meta(conv_id)
        if not meta or meta["count"] <= 0 or meta["min_id"] is None:
            return False
        if before_id is None:
            return True
        return meta["min_id"] < int(before_id)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_id(x) -> int:
        if isinstance(x, bytes):
            x = x.decode()
        return int(x)

    @staticmethod
    def _fetch_payloads(r, conv_id: int, msg_ids: List[int]) -> Optional[List[Dict]]:
        """Pipeline-GET payloads; None if any id is missing (incomplete window)."""
        if not msg_ids:
            return []
        pipe = r.pipeline(transaction=False)
        for mid in msg_ids:
            pipe.get(_msg_key(conv_id, mid))
        payloads = pipe.execute()
        messages: List[Dict] = []
        for mid, raw in zip(msg_ids, payloads):
            data = _json_loads(raw)
            if data is None:
                logger.warning(
                    "message_cache: missing payload for msg %s in conv %s",
                    mid, conv_id,
                )
                return None
            messages.append(data)
        return messages

    @staticmethod
    def get_cached_messages(
        conv_id: int,
        before_id: Optional[int],
        limit: int,
    ) -> Optional[Tuple[List[Dict], bool, Optional[int]]]:
        """
        Legacy helper: latest / before_id page.

        Return (messages_asc, has_more_older, next_before_id) or None on miss.
        Prefer ``get_message_window`` for around_id / after_id.
        """
        window = MessageCacheService.get_message_window(
            conv_id,
            before_id=before_id,
            after_id=None,
            around_id=None,
            limit=limit,
        )
        if window is None:
            return None
        return window["messages"], window["has_more"], window["next_before_id"]

    @staticmethod
    def touch_window_ttl(conv_id: int) -> None:
        """Refresh TTL on a live window so active chats stay hot."""
        ttl = _cache_ttl()
        if ttl <= 0:
            return
        r = _redis()
        if not r:
            return
        try:
            ids_key = _ids_key(conv_id)
            meta_key = _meta_key(conv_id)
            pipe = r.pipeline(transaction=False)
            pipe.expire(ids_key, ttl)
            pipe.expire(meta_key, ttl)
            # Touch a sample of payload keys is expensive; ids+meta is enough
            # to keep the index alive. Payloads keep their own TTL from write.
            pipe.execute()
        except Exception:
            pass

    @staticmethod
    def get_message_window(
        conv_id: int,
        *,
        before_id: Optional[int] = None,
        after_id: Optional[int] = None,
        around_id: Optional[int] = None,
        limit: int = 40,
    ) -> Optional[Dict[str, Any]]:
        """
        Serve a page from the hot window when the requested range is covered.

        Architecture
        ------------
        * Ordered id index:  ZSET ``msgcache:{conv}:ids`` (score = id)
        * Payloads:          STRING ``msgcache:{conv}:m:{id}``
        * Bounds:            HASH  ``msgcache:{conv}:meta`` {min_id, max_id, count}

        Window = contiguous **newest** ``MESSAGE_CACHE_SIZE`` messages.
        Reads are id-range chunks (not fixed page numbers).

        Returns dict:
          messages, has_more, next_before_id, has_more_newer, next_after_id
        or None on miss (caller uses Postgres).
        """
        r = _redis()
        if not r:
            return None

        meta = MessageCacheService.get_meta(conv_id)
        if not meta or meta["count"] <= 0 or meta["min_id"] is None or meta["max_id"] is None:
            record_miss("msg")
            return None

        min_id = int(meta["min_id"])
        max_id = int(meta["max_id"])
        limit = max(1, min(int(limit or 40), _cache_size()))
        ids_key = _ids_key(conv_id)

        try:
            # ==========================================================
            # around_id
            # ==========================================================
            if around_id is not None:
                around_id = int(around_id)
                if around_id < min_id or around_id > max_id:
                    record_miss("msg")
                    return None

                older_limit = max(1, limit // 2)
                newer_limit = max(1, limit - older_limit)

                older_raw = r.zrevrangebyscore(
                    ids_key, around_id, min_id, start=0, num=older_limit + 1
                ) or []
                has_more = len(older_raw) > older_limit
                older_ids = [
                    MessageCacheService._decode_id(x) for x in older_raw[:older_limit]
                ]
                older_ids.reverse()

                newer_raw = r.zrangebyscore(
                    ids_key, around_id + 1, max_id, start=0, num=newer_limit + 1
                ) or []
                has_more_newer = len(newer_raw) > newer_limit
                newer_ids = [
                    MessageCacheService._decode_id(x) for x in newer_raw[:newer_limit]
                ]

                msg_ids = older_ids + newer_ids
                messages = MessageCacheService._fetch_payloads(r, conv_id, msg_ids)
                if messages is None:
                    record_miss("msg")
                    return None

                # Older still in window above the first returned id?
                if older_ids and older_ids[0] > min_id:
                    has_more = True
                next_before = older_ids[0] if has_more and older_ids else None

                next_after = (
                    newer_ids[-1] if newer_ids else (older_ids[-1] if older_ids else None)
                )
                # Newer still in window below last returned?
                if next_after is not None and next_after < max_id:
                    has_more_newer = True
                elif next_after == max_id:
                    has_more_newer = False

                MessageCacheService.touch_window_ttl(conv_id)
                record_hit("msg")
                return {
                    "messages": messages,
                    "has_more": bool(has_more),
                    "next_before_id": next_before,
                    "has_more_newer": bool(has_more_newer),
                    "next_after_id": next_after,
                }

            # ==========================================================
            # after_id — newer messages toward live edge
            # ==========================================================
            if after_id is not None:
                after_id = int(after_id)
                if after_id >= max_id:
                    # Live edge already — empty newer page from cache
                    record_miss("msg")
                    return None
                # after_id must not leave a hole below the window
                if after_id < min_id - 1:
                    record_miss("msg")
                    return None

                raw = r.zrangebyscore(
                    ids_key, after_id + 1, max_id, start=0, num=limit + 1
                ) or []
                if not raw:
                    record_miss("msg")
                    return None

                has_more_newer = len(raw) > limit
                msg_ids = [MessageCacheService._decode_id(x) for x in raw[:limit]]
                messages = MessageCacheService._fetch_payloads(r, conv_id, msg_ids)
                if messages is None:
                    record_miss("msg")
                    return None

                next_after = msg_ids[-1]
                if next_after >= max_id:
                    has_more_newer = False
                elif len(raw) > limit:
                    has_more_newer = True
                else:
                    has_more_newer = next_after < max_id

                # Client can still scroll up into older history
                has_more = True
                next_before = after_id

                MessageCacheService.touch_window_ttl(conv_id)
                record_hit("msg")
                return {
                    "messages": messages,
                    "has_more": has_more,
                    "next_before_id": next_before,
                    "has_more_newer": bool(has_more_newer),
                    "next_after_id": next_after,
                }

            # ==========================================================
            # before_id / latest page
            # ==========================================================
            if not MessageCacheService.is_range_cached(conv_id, before_id, limit):
                record_miss("msg")
                return None

            max_score = (int(before_id) - 1) if before_id is not None else "+inf"
            raw_ids = r.zrevrangebyscore(
                ids_key, max_score, "-inf", start=0, num=limit + 1
            ) or []
            if not raw_ids:
                record_miss("msg")
                return None

            has_more = len(raw_ids) > limit
            msg_ids_desc = [MessageCacheService._decode_id(x) for x in raw_ids[:limit]]
            msg_ids_asc = list(reversed(msg_ids_desc))
            messages = MessageCacheService._fetch_payloads(r, conv_id, msg_ids_asc)
            if messages is None:
                record_miss("msg")
                return None

            # has_more (older) accuracy at the bottom of the hot window:
            # - If oldest returned id is still above min_id, more exists in cache.
            # - If oldest returned id == min_id, older messages may still exist in
            #   Postgres (outside the MESSAGE_CACHE_SIZE suffix). Signal has_more
            #   so the client issues another before_id request; that call misses
            #   cache (is_range_cached → False) and DB returns the truth.
            if messages:
                oldest = int(messages[0]["id"])
                if oldest > min_id:
                    has_more = True
                elif oldest == min_id:
                    has_more = True
            next_before = messages[0]["id"] if has_more and messages else None
            has_more_newer = before_id is not None
            next_after = messages[-1]["id"] if messages else None

            MessageCacheService.touch_window_ttl(conv_id)
            record_hit("msg")
            return {
                "messages": messages,
                "has_more": bool(has_more),
                "next_before_id": next_before,
                "has_more_newer": bool(has_more_newer),
                "next_after_id": next_after,
            }
        except Exception:
            logger.exception(
                "message_cache.get_message_window failed conv=%s", conv_id
            )
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

            # Drop previous id list + those payload keys (keep window tight)
            try:
                old_ids = r.zrange(ids_key, 0, -1) or []
            except Exception:
                old_ids = []
            new_id_set = {str(m.id) for m in sorted_msgs}

            pipe = r.pipeline(transaction=True)
            pipe.delete(ids_key)
            for x in old_ids:
                if isinstance(x, bytes):
                    x = x.decode()
                if str(x) not in new_id_set:
                    pipe.delete(_msg_key(conv_id, int(x)))

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
        """Reload the latest MESSAGE_CACHE_SIZE messages from Postgres.

        Uses a short Redis lock so concurrent MISS traffic does not stampede
        the database with identical rebuilds.
        """
        from .models import Message

        r = _redis()
        lock_key = f"{_PREFIX}:{conv_id}:rebuild_lock"
        if r:
            try:
                # nx + short TTL: only one rebuild at a time per conversation
                got = r.set(lock_key, "1", nx=True, ex=45)
                if not got:
                    return
            except Exception:
                pass

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
        finally:
            if r:
                try:
                    r.delete(lock_key)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Incremental updates (after successful DB commit)
    # ------------------------------------------------------------------

    @staticmethod
    def add_message(msg) -> None:
        """Insert a newly created message into the hot window (sliding).

        List (ZSET) and payload (STRING) stay in sync: when the window exceeds
        MESSAGE_CACHE_SIZE, the oldest ids are dropped from the ZSET **and**
        their payload keys are deleted.
        """
        r = _redis()
        if not r:
            return
        conv_id = msg.conversation_id
        size = _cache_size()
        ttl = _cache_ttl()
        try:
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

            # Snapshot ids that will fall out of the window after this insert
            # (rank 0 .. count-size-1 become excess once count becomes size+1)
            try:
                excess = r.zrange(ids_key, 0, -(size))  # may include ids to drop after add
            except Exception:
                excess = []

            pipe = r.pipeline(transaction=True)
            pipe.set(msg_key, _json_dumps(payload))
            pipe.zadd(ids_key, {str(mid): mid})
            pipe.zremrangebyrank(ids_key, 0, -(size + 1))
            if ttl > 0:
                pipe.expire(msg_key, ttl)
                pipe.expire(ids_key, ttl)
            pipe.execute()

            # Delete payload keys for ids no longer in the ZSET
            try:
                still = set()
                for x in r.zrange(ids_key, 0, -1) or []:
                    if isinstance(x, bytes):
                        x = x.decode()
                    still.add(str(x))
                drop = []
                for x in excess or []:
                    if isinstance(x, bytes):
                        x = x.decode()
                    if str(x) not in still and str(x) != str(mid):
                        drop.append(_msg_key(conv_id, int(x)))
                if drop:
                    r.delete(*drop)
            except Exception:
                logger.exception("message_cache.add_message orphan cleanup failed")

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

        # Which view-once attachments this viewer already opened
        vo_opened_ids = set()
        if viewer_id:
            try:
                from .models import AttachmentViewOnceOpen
                att_ids = []
                for m in base_messages:
                    for a in (m.get("attachments") or []):
                        if isinstance(a, dict) and a.get("is_view_once") and a.get("id"):
                            att_ids.append(int(a["id"]))
                if att_ids:
                    vo_opened_ids = set(
                        AttachmentViewOnceOpen.objects.filter(
                            attachment_id__in=att_ids, user_id=viewer_id
                        ).values_list("attachment_id", flat=True)
                    )
            except Exception:
                logger.exception("enrich_for_viewer: view-once opens lookup failed")

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


        # Viewer-aware avatars / online / bio
        user_ids = set()
        for m in base_messages:
            s = m.get("sender") or {}
            if s.get("id"):
                user_ids.add(int(s["id"]))
            rp = (m.get("reply_to_preview") or {}).get("sender") or {}
            if rp.get("id"):
                user_ids.add(int(rp["id"]))
            ff = m.get("forwarded_from_user") or {}
            if ff.get("id"):
                user_ids.add(int(ff["id"]))
        avatar_map = {}
        bio_map = {}
        online_ids = set()
        contact_ids = set()
        blocked_ids = set()
        if request is not None and user_ids:
            try:
                from .serializers import build_user_mini_context
                uctx = build_user_mini_context(request, list(user_ids))
                avatar_map = uctx.get("avatar_map") or {}
                bio_map = uctx.get("bio_map") or {}
                online_ids = uctx.get("online_ids") or set()
                contact_ids = uctx.get("contact_ids") or set()
                blocked_ids = uctx.get("blocked_ids") or set()
            except Exception:
                logger.exception("enrich_for_viewer: build_user_mini_context failed")

        def _patch_user(u):
            if not isinstance(u, dict) or not u.get("id"):
                return u
            uid = int(u["id"])
            out_u = dict(u)
            if uid in avatar_map:
                out_u["avatar"] = avatar_map.get(uid)
            elif "avatar" not in out_u:
                out_u["avatar"] = None
            out_u["bio"] = bio_map.get(uid, out_u.get("bio") or "") or ""
            out_u["is_online"] = uid in online_ids
            out_u["is_contact"] = uid in contact_ids
            out_u["is_blocked"] = uid in blocked_ids
            return out_u

        result = []
        for m in base_messages:
            out = dict(m)
            out["_vo_opened"] = vo_opened_ids
            mid = out["id"]
            agg = out.get("reactions_agg") or {}
            mine = mine_map.get(mid) or set()
            out["reactions"] = [
                {"emoji": em, "count": int(cnt), "mine": em in mine}
                for em, cnt in sorted(agg.items())
            ]
            out.pop("reactions_agg", None)

            # View-once attachment states for viewer
            atts = out.get("attachments")
            if isinstance(atts, list) and atts:
                patched = []
                for a in atts:
                    if not isinstance(a, dict):
                        patched.append(a)
                        continue
                    ad = dict(a)
                    if ad.get("is_purged"):
                        ad["url"] = None
                        ad["view_once_state"] = "purged"
                    elif ad.get("is_view_once"):
                        snd = (out.get("sender") or {}).get("id")
                        if viewer_id and snd and int(viewer_id) == int(snd):
                            ad["view_once_state"] = "own"
                            ad["url"] = f"/api/messenger/attachments/{ad.get('id')}/download/"
                        elif ad.get("id") in (out.get("_vo_opened") or set()):
                            ad["view_once_state"] = "opened"
                            ad["url"] = None
                        else:
                            ad["view_once_state"] = "pending"
                            ad["url"] = None
                    patched.append(ad)
                out["attachments"] = patched

            if out.get("sender"):
                out["sender"] = _patch_user(out["sender"])
            rtp = out.get("reply_to_preview")
            if isinstance(rtp, dict) and rtp.get("sender"):
                rtp = dict(rtp)
                rtp["sender"] = _patch_user(rtp["sender"])
                out["reply_to_preview"] = rtp
            if out.get("forwarded_from_user"):
                out["forwarded_from_user"] = _patch_user(out["forwarded_from_user"])

            if out.get("is_system") or out.get("is_deleted"):
                out["read_state"] = "read"
            elif not viewer_id or not out.get("sender") or out["sender"].get("id") != viewer_id:
                out["read_state"] = "read"
            else:
                out["read_state"] = "read" if mid in read_ids else "sent"

            out.pop("_vo_opened", None)
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
            _incr_stat("list_set_fail")
            return
        try:
            ttl = _list_ttl()
            key = _user_list_key(user_id)
            raw = _json_dumps(payload)
            r.set(key, raw)
            if ttl > 0:
                r.expire(key, ttl)
            _incr_stat("list_set_ok")
        except Exception:
            _incr_stat("list_set_fail")
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
    """Update one message in the hot window. Does NOT bust conversation-list cache.

    List previews only need last_message text on *new* messages / deletes;
    reactions and body edits of older rows should not force a full list rebuild.
    """
    msg_id = getattr(msg, "id", None)

    def _job():
        from .models import Message
        fresh = Message.objects.filter(pk=msg_id).first()
        if fresh:
            MessageCacheService.update_message(fresh)

    run_after_commit(_job)


def schedule_delete_message(conv_id: int, msg_id: int) -> None:
    def _job():
        MessageCacheService.delete_message(conv_id, msg_id)
        ConversationCacheService.invalidate_conv_lists_for_conversation(conv_id)

    run_after_commit(_job)
