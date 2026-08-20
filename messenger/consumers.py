"""Messenger WebSocket — personal + per-conversation rooms.

Presence tracking: when a user connects, we set a cache key and broadcast a
`presence.update` event to all conversations that user is part of. When they
disconnect, we clear the key and broadcast again. This powers the green online
dot on avatars in the chat list, chat header, and profile views.
"""
from __future__ import annotations

import logging
import urllib.parse

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()
logger = logging.getLogger("messenger.ws")

# Presence: connection-counted + short TTL (refreshed by ping without rebroadcast)
ONLINE_KEY = "messenger:online:{uid}"
ONLINE_CONNS_KEY = "messenger:online_conns:{uid}"
ONLINE_TTL = 90  # seconds — must exceed client ping interval (~25s)


def _touch_online_flag(user_id: int) -> None:
    try:
        cache.set(ONLINE_KEY.format(uid=user_id), True, ONLINE_TTL)
    except Exception:
        pass


def set_user_online(user_id: int, *, broadcast: bool = True) -> None:
    """Register one live WS connection. Broadcast only on 0 → 1 transition (or forced)."""
    if not user_id:
        return
    key = ONLINE_CONNS_KEY.format(uid=user_id)
    was_online = False
    try:
        was_online = bool(cache.get(ONLINE_KEY.format(uid=user_id)))
        # Increment connection count
        try:
            n = cache.incr(key)
        except ValueError:
            cache.set(key, 1, ONLINE_TTL + 60)
            n = 1
        except Exception:
            n = 1
            try:
                cache.set(key, 1, ONLINE_TTL + 60)
            except Exception:
                pass
        else:
            try:
                cache.touch(key, ONLINE_TTL + 60)
            except Exception:
                try:
                    cache.set(key, n, ONLINE_TTL + 60)
                except Exception:
                    pass
        _touch_online_flag(user_id)
        # Only announce when newly online
        if broadcast and (not was_online or n == 1):
            _broadcast_presence(user_id, True)
    except Exception:
        logger.exception("set_user_online failed uid=%s", user_id)
        _touch_online_flag(user_id)
        if broadcast:
            _broadcast_presence(user_id, True)


def refresh_user_online(user_id: int) -> None:
    """Ping heartbeat: extend TTL only — do NOT rebroadcast (avoids permanent 'online' spam)."""
    if not user_id:
        return
    try:
        conns = cache.get(ONLINE_CONNS_KEY.format(uid=user_id))
        if not conns:
            # Stale flag without connections — clear
            try:
                cache.delete(ONLINE_KEY.format(uid=user_id))
            except Exception:
                pass
            return
        _touch_online_flag(user_id)
        try:
            cache.touch(ONLINE_CONNS_KEY.format(uid=user_id), ONLINE_TTL + 60)
        except Exception:
            try:
                cache.set(ONLINE_CONNS_KEY.format(uid=user_id), int(conns), ONLINE_TTL + 60)
            except Exception:
                pass
    except Exception:
        logger.exception("refresh_user_online failed uid=%s", user_id)


def set_user_offline(user_id: int) -> None:
    """Drop one connection. Broadcast offline only when the last connection closes."""
    if not user_id:
        return
    key = ONLINE_CONNS_KEY.format(uid=user_id)
    try:
        try:
            n = cache.decr(key)
        except ValueError:
            n = 0
        except Exception:
            n = 0
        if n is None or n < 0:
            n = 0
        if n <= 0:
            try:
                cache.delete(key)
            except Exception:
                pass
            try:
                cache.delete(ONLINE_KEY.format(uid=user_id))
            except Exception:
                pass
            _broadcast_presence(user_id, False)
        else:
            # Still have other tabs/devices
            _touch_online_flag(user_id)
    except Exception:
        logger.exception("set_user_offline failed uid=%s", user_id)
        try:
            cache.delete(ONLINE_KEY.format(uid=user_id))
            cache.delete(key)
        except Exception:
            pass
        _broadcast_presence(user_id, False)


def is_user_online(user_id: int) -> bool:
    """Check if a user is currently online (cache-based)."""
    if not user_id:
        return False
    try:
        if not bool(cache.get(ONLINE_KEY.format(uid=user_id))):
            return False
        conns = cache.get(ONLINE_CONNS_KEY.format(uid=user_id))
        if conns is not None and int(conns) <= 0:
            return False
        return True
    except Exception:
        return False


def _broadcast_presence(user_id: int, online: bool) -> None:
    """Notify conversation rooms AND every peer's personal channel (chat-list viewers)."""
    from .models import ConversationParticipant

    try:
        conv_ids = list(
            ConversationParticipant.objects.filter(
                user_id=user_id, left_at__isnull=True
            ).values_list("conversation_id", flat=True)
        )
    except Exception:
        conv_ids = []

    data = {
        "type": "presence.update",
        "user_id": int(user_id),
        "online": bool(online),
    }
    for cid in conv_ids:
        _send(f"messenger_conv_{cid}", data)

    # Peers on the conversation list may only be in messenger_user_{peer}
    peer_ids = set()
    if conv_ids:
        try:
            peer_ids = set(
                ConversationParticipant.objects.filter(
                    conversation_id__in=conv_ids,
                    left_at__isnull=True,
                )
                .exclude(user_id=user_id)
                .values_list("user_id", flat=True)
                .distinct()[:2000]
            )
        except Exception:
            peer_ids = set()
    for pid in peer_ids:
        _send(f"messenger_user_{pid}", data)
    # Own other tabs
    _send(f"messenger_user_{user_id}", data)



async def authenticate_from_scope(scope):
    query = scope.get("query_string", b"").decode("utf-8")
    params = urllib.parse.parse_qs(query)
    access_token = (params.get("token") or [None])[0]
    if not access_token:
        return None
    try:
        validated = AccessToken(access_token)
        user_id = validated["user_id"]
    except (InvalidToken, TokenError, KeyError):
        return None
    try:
        user = await database_sync_to_async(
            User.objects.only("id", "is_active", "username").get
        )(pk=user_id)
    except User.DoesNotExist:
        return None
    if not user.is_active:
        return None
    return user


class MessengerConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = await authenticate_from_scope(self.scope)
        if not user:
            await self.close(code=4401)
            return
        self.user = user
        self.groups_joined = []
        g = f"messenger_user_{user.id}"
        await self.channel_layer.group_add(g, self.channel_name)
        self.groups_joined.append(g)
        await self.accept()
        await self.send_json({"type": "connected", "user_id": user.id})
        # Presence: mark online and broadcast
        await database_sync_to_async(set_user_online)(user.id)
        # Deliver any still-ringing calls (user was offline when call started)
        try:
            pending = await database_sync_to_async(_pending_ringing_for_user)(user.id)
            for item in pending:
                await self.send_json(item)
        except Exception:
            pass

    async def disconnect(self, code):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(g, self.channel_name)
        if getattr(self, "user", None):
            await database_sync_to_async(set_user_offline)(self.user.id)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        t = content.get("type")
        if t == "ping":
            # Heartbeat only — do not rebroadcast online (that caused sticky presence)
            if getattr(self, "user", None):
                await database_sync_to_async(refresh_user_online)(self.user.id)
                # Re-check ringing calls (covers offline→online within 30s window)
                try:
                    pending = await database_sync_to_async(_pending_ringing_for_user)(self.user.id)
                    for item in pending:
                        await self.send_json(item)
                except Exception:
                    pass
            await self.send_json({"type": "pong"})
            return
        if t == "subscribe":
            try:
                cid = int(content.get("conversation_id"))
            except (TypeError, ValueError):
                return
            allowed = await database_sync_to_async(self._can_subscribe)(cid)
            if not allowed:
                await self.send_json({"type": "error", "detail": "forbidden"})
                return
            g = f"messenger_conv_{cid}"
            if g not in self.groups_joined:
                await self.channel_layer.group_add(g, self.channel_name)
                self.groups_joined.append(g)
            await self.send_json({"type": "subscribed", "conversation_id": cid})
            return
        if t == "unsubscribe":
            try:
                cid = int(content.get("conversation_id"))
            except (TypeError, ValueError):
                return
            g = f"messenger_conv_{cid}"
            if g in self.groups_joined:
                await self.channel_layer.group_discard(g, self.channel_name)
                self.groups_joined.remove(g)
            return

        if t == "typing":
            # { type: "typing", conversation_id, is_typing: true|false }
            try:
                cid = int(content.get("conversation_id"))
            except (TypeError, ValueError):
                return
            if not getattr(self, "user", None):
                return
            allowed = await database_sync_to_async(self._can_subscribe)(cid)
            if not allowed:
                return
            is_typing = bool(content.get("is_typing", True))
            username = getattr(self.user, "username", "") or ""
            data = {
                "type": "typing",
                "conversation_id": cid,
                "user_id": self.user.id,
                "username": username,
                "is_typing": is_typing,
            }
            await self.channel_layer.group_send(
                f"messenger_conv_{cid}",
                {"type": "messenger.event", "data": data},
            )
            return

        if t == "draft":
            # { type: "draft", conversation_id, text }
            try:
                cid = int(content.get("conversation_id"))
            except (TypeError, ValueError):
                return
            if not getattr(self, "user", None):
                return
            allowed = await database_sync_to_async(self._can_subscribe)(cid)
            if not allowed:
                return
            draft_text = content.get("text")
            if draft_text is None:
                draft_text = ""
            draft_text = str(draft_text)[:20000]
            await database_sync_to_async(self._save_draft)(cid, draft_text)
            # Push to this user's other devices (user channel group)
            data = {
                "type": "draft",
                "conversation_id": cid,
                "user_id": self.user.id,
                "text": draft_text,
            }
            await self.channel_layer.group_send(
                f"messenger_user_{self.user.id}",
                {"type": "messenger.event", "data": data},
            )
            return

        if t == "emoji_play":
            # { type: "emoji_play", conversation_id, message_id }
            try:
                cid = int(content.get("conversation_id"))
                mid = int(content.get("message_id"))
            except (TypeError, ValueError):
                return
            if not getattr(self, "user", None):
                return
            allowed = await database_sync_to_async(self._can_subscribe)(cid)
            if not allowed:
                return
            data = {
                "type": "emoji_play",
                "conversation_id": cid,
                "message_id": mid,
                "user_id": self.user.id,
            }
            await self.channel_layer.group_send(
                f"messenger_conv_{cid}",
                {"type": "messenger.event", "data": data},
            )
            return

    def _can_subscribe(self, conversation_id: int) -> bool:
        from .models import ConversationParticipant
        return ConversationParticipant.objects.filter(
            conversation_id=conversation_id, user_id=self.user.id, left_at__isnull=True
        ).exists()

    def _save_draft(self, conversation_id: int, text: str) -> None:
        from django.utils import timezone
        from .models import ConversationParticipant
        ConversationParticipant.objects.filter(
            conversation_id=conversation_id, user_id=self.user.id, left_at__isnull=True
        ).update(draft_text=text, draft_updated_at=timezone.now())

    async def messenger_event(self, event):
        data = event.get("data") or {}
        # Don't echo typing events back to the sender
        if data.get("type") == "typing" and data.get("user_id") == getattr(self.user, "id", None):
            return
        await self.send_json(data)


def _send(group: str, data: dict):
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": "messenger.event", "data": data})
    except Exception:
        logger.exception("group_send failed %s", group)


def broadcast_message(msg):
    data = {
        "type": "message.new",
        "conversation_id": msg.conversation_id,
        "message_id": msg.id,
        "sender_id": msg.sender_id,
        "body": (msg.body or "")[:200],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
    _send(f"messenger_conv_{msg.conversation_id}", data)
    # Notify all participants personally
    from .models import ConversationParticipant
    for uid in ConversationParticipant.objects.filter(
        conversation_id=msg.conversation_id, left_at__isnull=True
    ).values_list("user_id", flat=True):
        if uid != msg.sender_id:
            _send(f"messenger_user_{uid}", data)


def broadcast_reaction(msg, user, emoji, action):
    data = {
        "type": "message.reaction",
        "conversation_id": msg.conversation_id,
        "message_id": msg.id,
        "user_id": user.id,
        "emoji": emoji,
        "action": action,
    }
    _send(f"messenger_conv_{msg.conversation_id}", data)




def broadcast_call_event(conversation_id, data, exclude_user_id=None):
    """Fan-out call.started / call.ended to conversation participants."""
    from .models import ConversationParticipant
    payload = dict(data)
    payload.setdefault("conversation_id", conversation_id)
    _send(f"messenger_conv_{conversation_id}", payload)
    for uid in ConversationParticipant.objects.filter(
        conversation_id=conversation_id, left_at__isnull=True
    ).values_list("user_id", flat=True):
        if exclude_user_id and uid == exclude_user_id:
            continue
        _send(f"messenger_user_{uid}", payload)


def broadcast_read(conversation_id, reader_user_id, receipts):
    """Notify the conversation that some messages were just read by `reader_user_id`.
    Senders flip their tick state from 'sent' -> 'read'.
    """
    if not receipts:
        return
    data = {
        "type": "message.read",
        "conversation_id": conversation_id,
        "reader_id": reader_user_id,
        "message_ids": [r["message_id"] for r in receipts],
    }
    # Notify every participant (including the reader — harmless)
    from .models import ConversationParticipant
    for uid in ConversationParticipant.objects.filter(
        conversation_id=conversation_id, left_at__isnull=True
    ).values_list("user_id", flat=True):
        if uid != reader_user_id:
            _send(f"messenger_user_{uid}", data)
    _send(f"messenger_conv_{conversation_id}", data)


def broadcast_member_change(conversation_id, data: dict):
    """Broadcast a member-level change (remove, role change, transfer, leave)
    to all participants of the conversation so they reload the detail.

    For removals, we ALSO send the event to the removed user's personal channel
    (even though they're no longer an active participant) so their client can
    redirect them out of the chat.
    """
    from .models import ConversationParticipant
    _send(f"messenger_conv_{conversation_id}", data)
    # Active participants (still in the group)
    active_ids = set(
        ConversationParticipant.objects.filter(
            conversation_id=conversation_id, left_at__isnull=True
        ).values_list("user_id", flat=True)
    )
    for uid in active_ids:
        _send(f"messenger_user_{uid}", data)
    # If this is a removal, also notify the removed user (now inactive).
    # Their `left_at` is set, so the loop above skipped them.
    if data.get("type") == "member.removed" and data.get("user_id"):
        removed_uid = data.get("user_id")
        if removed_uid not in active_ids:
            _send(f"messenger_user_{removed_uid}", data)
    # For "member.left" events, the leaver is still in active_ids at the time
    # of broadcast (their `left_at` was set BEFORE broadcast), so they WILL
    # receive the event via the loop above. We also explicitly send to them
    # so their client redirects out even if they had already unsubscribed
    # from the conversation channel.
    if data.get("type") == "member.left" and data.get("user_id"):
        leaver_uid = data.get("user_id")
        _send(f"messenger_user_{leaver_uid}", data)


def broadcast_profile_update(user_id: int):
    """Notify all conversations the user is part of that their profile changed.

    Frontend will reload conversation list + active conversation detail to pick
    up the new avatar/username/bio. This makes profile photo changes propagate
    to every chat, group, and channel the user is part of in real time.
    """
    from .models import ConversationParticipant
    data = {
        "type": "profile.update",
        "user_id": user_id,
    }
    try:
        conv_ids = list(
            ConversationParticipant.objects.filter(
                user_id=user_id, left_at__isnull=True
            ).values_list("conversation_id", flat=True)
        )
    except Exception:
        return
    for cid in conv_ids:
        _send(f"messenger_conv_{cid}", data)
    # Also notify the user's own personal channel so other tabs update too
    _send(f"messenger_user_{user_id}", data)


def broadcast_join_request(conversation_id, data: dict):
    """Notify admins of a group about a new join request (or status change).

    Only owners/admins receive this — they see the request in their
    "Join requests" panel.
    """
    from .models import ConversationParticipant
    admin_ids = list(
        ConversationParticipant.objects.filter(
            conversation_id=conversation_id,
            role__in=["owner", "admin"],
            left_at__isnull=True,
        ).values_list("user_id", flat=True)
    )
    for uid in admin_ids:
        _send(f"messenger_user_{uid}", data)
    # Also send to the requesting user so their "My Requests" panel updates
    if data.get("user_id"):
        _send(f"messenger_user_{data['user_id']}", data)


def broadcast_pin(conversation_id, data: dict):
    """Broadcast a message pin/unpin event to all participants in a conversation.

    Every participant's pinned-message bar should update in real-time.
    """
    from .models import ConversationParticipant
    _send(f"messenger_conv_{conversation_id}", data)
    for uid in ConversationParticipant.objects.filter(
        conversation_id=conversation_id, left_at__isnull=True
    ).values_list("user_id", flat=True):
        _send(f"messenger_user_{uid}", data)
