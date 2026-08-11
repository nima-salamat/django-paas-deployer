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

# Cache key helpers — TTL of 120s; refreshed by ping
ONLINE_KEY = "messenger:online:{uid}"
ONLINE_TTL = 120  # seconds


def set_user_online(user_id: int):
    """Mark a user as online in cache and broadcast presence to their conversations."""
    try:
        cache.set(ONLINE_KEY.format(uid=user_id), True, ONLINE_TTL)
    except Exception:
        pass
    _broadcast_presence(user_id, True)


def set_user_offline(user_id: int):
    """Mark a user as offline and broadcast presence."""
    try:
        cache.delete(ONLINE_KEY.format(uid=user_id))
    except Exception:
        pass
    _broadcast_presence(user_id, False)


def is_user_online(user_id: int) -> bool:
    """Check if a user is currently online (cache-based)."""
    if not user_id:
        return False
    try:
        return bool(cache.get(ONLINE_KEY.format(uid=user_id)))
    except Exception:
        return False


def _broadcast_presence(user_id: int, online: bool):
    """Send presence.update to every conversation the user is part of."""
    from .models import ConversationParticipant
    try:
        conv_ids = list(
            ConversationParticipant.objects.filter(
                user_id=user_id, left_at__isnull=True
            ).values_list("conversation_id", flat=True)
        )
    except Exception:
        return
    data = {
        "type": "presence.update",
        "user_id": user_id,
        "online": online,
    }
    for cid in conv_ids:
        _send(f"messenger_conv_{cid}", data)
    # Also notify the user's personal channel (so other tabs update)
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
            # Refresh online presence on ping
            if getattr(self, "user", None):
                await database_sync_to_async(set_user_online)(self.user.id)
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

    def _can_subscribe(self, conversation_id: int) -> bool:
        from .models import ConversationParticipant
        return ConversationParticipant.objects.filter(
            conversation_id=conversation_id, user_id=self.user.id, left_at__isnull=True
        ).exists()

    async def messenger_event(self, event):
        await self.send_json(event.get("data") or {})


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
    """
    from .models import ConversationParticipant
    _send(f"messenger_conv_{conversation_id}", data)
    for uid in ConversationParticipant.objects.filter(
        conversation_id=conversation_id, left_at__isnull=True
    ).values_list("user_id", flat=True):
        _send(f"messenger_user_{uid}", data)
