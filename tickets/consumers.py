"""Ticket WebSockets — staff feed + personal notify (JWT via ?token=)."""
from __future__ import annotations

import logging
import urllib.parse

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()
logger = logging.getLogger("tickets.ws")


async def authenticate_from_scope(scope):
    query = scope.get("query_string", b"").decode("utf-8")
    params = urllib.parse.parse_qs(query)
    access_token = (params.get("token") or [None])[0]
    if not access_token:
        return None
    try:
        validated = AccessToken(access_token)
        user_id = validated["user_id"]
    except (InvalidToken, TokenError, KeyError) as exc:
        logger.info("tickets.ws bad token: %s", type(exc).__name__)
        return None
    try:
        user = await database_sync_to_async(
            User.objects.only("id", "is_active", "is_staff", "is_superuser", "username").get
        )(pk=user_id)
    except User.DoesNotExist:
        return None
    if not user.is_active:
        return None
    return user


class TicketEventsConsumer(AsyncJsonWebsocketConsumer):
    """Staff-only live feed (legacy path /ws/tickets/)."""

    async def connect(self):
        user = await authenticate_from_scope(self.scope)
        if not user or not (user.is_staff or user.is_superuser):
            await self.close(code=4403)
            return
        self.user = user
        self.groups_joined = []
        # All staff hear the global staff channel
        await self.channel_layer.group_add("tickets_staff_all", self.channel_name)
        self.groups_joined.append("tickets_staff_all")
        await self.accept()
        await self.send_json({"type": "connected", "channel": "staff"})

    async def disconnect(self, code):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(g, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def ticket_event(self, event):
        await self.send_json(event.get("data") or {})


class TicketNotifyConsumer(AsyncJsonWebsocketConsumer):
    """
    Personal + staff notification channel for any logged-in user.
    Path: /ws/tickets/notify/?token=<jwt>
    """

    async def connect(self):
        user = await authenticate_from_scope(self.scope)
        if not user:
            await self.close(code=4401)
            return
        self.user = user
        self.groups_joined = []

        # Personal inbox
        g = f"tickets_user_{user.id}"
        await self.channel_layer.group_add(g, self.channel_name)
        self.groups_joined.append(g)

        # All staff get support-wide events
        if user.is_staff or user.is_superuser:
            await self.channel_layer.group_add("tickets_staff_all", self.channel_name)
            self.groups_joined.append("tickets_staff_all")

        await self.accept()
        await self.send_json({
            "type": "connected",
            "channel": "notify",
            "user_id": user.id,
            "is_staff": bool(user.is_staff or user.is_superuser),
        })
        logger.info("tickets.ws notify connected user=%s staff=%s", user.id, user.is_staff)

    async def disconnect(self, code):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(g, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        t = content.get("type")
        if t == "ping":
            await self.send_json({"type": "pong"})
            return
        if t == "subscribe_ticket":
            try:
                tid = int(content.get("ticket_id"))
            except (TypeError, ValueError):
                return
            allowed = await database_sync_to_async(self._can_subscribe)(tid)
            if not allowed:
                await self.send_json({"type": "error", "detail": "forbidden"})
                return
            g = f"tickets_ticket_{tid}"
            if g not in self.groups_joined:
                await self.channel_layer.group_add(g, self.channel_name)
                self.groups_joined.append(g)
            await self.send_json({"type": "subscribed", "ticket_id": tid})
            return
        if t == "unsubscribe_ticket":
            try:
                tid = int(content.get("ticket_id"))
            except (TypeError, ValueError):
                return
            g = f"tickets_ticket_{tid}"
            if g in self.groups_joined:
                await self.channel_layer.group_discard(g, self.channel_name)
                self.groups_joined.remove(g)

    def _can_subscribe(self, ticket_id: int) -> bool:
        from .models import Ticket
        if self.user.is_staff or self.user.is_superuser:
            return Ticket.objects.filter(pk=ticket_id).exists()
        return Ticket.objects.filter(pk=ticket_id, user_id=self.user.id).exists()

    async def ticket_event(self, event):
        await self.send_json(event.get("data") or {})


def broadcast_ticket_event(event_type: str, ticket, extra=None):
    """Fan-out minimal event to staff, owner, and ticket room."""
    layer = get_channel_layer()
    if layer is None:
        logger.warning("tickets.ws no channel layer")
        return

    payload = {
        "type": event_type,
        "ticket_id": ticket.id,
        "public_id": getattr(ticket, "public_id", None),
        "subject": (getattr(ticket, "subject", None) or "")[:120],
        "status": getattr(ticket, "status", None),
        "priority": getattr(ticket, "priority", None),
        "department_id": getattr(ticket, "department_id", None),
        "user_id": getattr(ticket, "user_id", None),
    }
    if extra:
        for k in (
            "message_id", "message_ids", "is_staff_reply", "author_id",
            "reader_id", "marked", "is_staff", "preview", "username",
        ):
            if k in extra:
                payload[k] = extra[k]

    message = {"type": "ticket.event", "data": payload}

    def _send(group):
        try:
            async_to_sync(layer.group_send)(group, message)
        except Exception as exc:
            logger.exception("tickets.ws group_send %s failed: %s", group, exc)

    _send("tickets_staff_all")
    uid = getattr(ticket, "user_id", None)
    if uid:
        _send(f"tickets_user_{uid}")
    _send(f"tickets_ticket_{ticket.id}")
    logger.info("tickets.ws broadcast %s ticket=%s", event_type, ticket.id)
