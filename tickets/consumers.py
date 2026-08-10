"""Ticket WebSockets: staff events + personal notify channel."""
from __future__ import annotations

import logging
import urllib.parse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()
logger = logging.getLogger("tickets.ws")

CODE_NO_TOKEN = 4401
CODE_BAD_TOKEN = 4402
CODE_FORBIDDEN = 4403
CODE_RATE_LIMIT = 4429
CODE_BAD_ORIGIN = 4403


def _client_ip(scope) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-for", b"").decode("latin1").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    client = scope.get("client")
    return (client[0] if client else "unknown")[:64]


def _origin_allowed(scope) -> bool:
    headers = dict(scope.get("headers") or [])
    origin = headers.get(b"origin", b"").decode("latin1").strip()
    if not origin:
        return bool(getattr(settings, "DEBUG", False))
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        return True
    allowed = set()
    for h in getattr(settings, "ALLOWED_HOSTS", []) or []:
        if h and h != "*":
            allowed.add(f"https://{h}")
            allowed.add(f"http://{h}")
    for attr in ("DOMAIN_NAME", "API_DOMAIN_NAME"):
        d = getattr(settings, attr, None) or ""
        if d:
            allowed.add(f"https://{d}")
            allowed.add(f"http://{d}")
    for o in getattr(settings, "CORS_ALLOWED_ORIGINS", None) or []:
        allowed.add(str(o).rstrip("/"))
    if not allowed:
        return True
    return origin.rstrip("/") in allowed


@database_sync_to_async
def _is_token_blacklisted(jti: str) -> bool:
    if not jti:
        return False
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        return BlacklistedToken.objects.filter(token__jti=jti).exists()
    except Exception:
        return False


@database_sync_to_async
def _get_user(user_id: int):
    return User.objects.only(
        "id", "is_active", "is_staff", "is_superuser", "username"
    ).get(pk=user_id)


@database_sync_to_async
def _dept_ids_for(user_id: int):
    from .models import DepartmentMembership
    return list(
        DepartmentMembership.objects.filter(user_id=user_id).values_list(
            "department_id", flat=True
        )
    )


@database_sync_to_async
def _user_owns_ticket(user_id: int, ticket_id: int) -> bool:
    from .models import Ticket
    return Ticket.objects.filter(pk=ticket_id, user_id=user_id).exists()


async def _authenticate(scope):
    if not _origin_allowed(scope):
        return None, CODE_BAD_ORIGIN
    query = scope.get("query_string", b"").decode("utf-8")
    params = urllib.parse.parse_qs(query)
    access_token = (params.get("token") or [None])[0]
    if not access_token or len(access_token) > 4096:
        return None, CODE_NO_TOKEN
    ip = _client_ip(scope)
    rl_key = f"ws:tickets:conn:{ip}"
    try:
        n = cache.get(rl_key)
        if n is not None and int(n) >= 40:
            return None, CODE_RATE_LIMIT
        if n is None:
            cache.set(rl_key, 1, timeout=60)
        else:
            try:
                cache.incr(rl_key)
            except ValueError:
                cache.set(rl_key, 1, timeout=60)
    except Exception:
        pass
    try:
        validated = AccessToken(access_token)
        user_id = validated["user_id"]
        jti = validated.get("jti")
    except (InvalidToken, TokenError, KeyError):
        return None, CODE_BAD_TOKEN
    if await _is_token_blacklisted(jti):
        return None, CODE_BAD_TOKEN
    try:
        user = await _get_user(user_id)
    except User.DoesNotExist:
        return None, CODE_BAD_TOKEN
    if not user.is_active:
        return None, CODE_FORBIDDEN
    return user, None


class TicketEventsConsumer(AsyncJsonWebsocketConsumer):
    """Staff/admin department-scoped live ticket feed."""

    async def connect(self):
        user, err = await _authenticate(self.scope)
        if err:
            await self.close(code=err)
            return
        if not (user.is_staff or user.is_superuser):
            await self.close(code=CODE_FORBIDDEN)
            return
        self.user = user
        self.groups_joined = []
        if user.is_superuser:
            await self.channel_layer.group_add("tickets_staff_all", self.channel_name)
            self.groups_joined.append("tickets_staff_all")
        else:
            for did in await _dept_ids_for(user.id):
                g = f"tickets_dept_{did}"
                await self.channel_layer.group_add(g, self.channel_name)
                self.groups_joined.append(g)
        await self.accept()
        await self.send_json({"type": "connected", "channel": "staff", "groups": len(self.groups_joined)})

    async def disconnect(self, code):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(g, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def ticket_event(self, event):
        data = event.get("data") or {}
        if not getattr(self.user, "is_superuser", False):
            dept_id = data.get("department_id")
            allowed = {
                g.replace("tickets_dept_", "")
                for g in self.groups_joined
                if g.startswith("tickets_dept_")
            }
            if dept_id is not None and str(dept_id) not in allowed:
                return
        await self.send_json(data)


class TicketNotifyConsumer(AsyncJsonWebsocketConsumer):
    """
    Personal notification channel for any authenticated user.
    Joins tickets_user_<id> and optionally tickets_ticket_<id> via subscribe.
    """

    async def connect(self):
        user, err = await _authenticate(self.scope)
        if err:
            await self.close(code=err)
            return
        self.user = user
        self.groups_joined = []
        g = f"tickets_user_{user.id}"
        await self.channel_layer.group_add(g, self.channel_name)
        self.groups_joined.append(g)
        if user.is_staff or user.is_superuser:
            if user.is_superuser:
                await self.channel_layer.group_add("tickets_staff_all", self.channel_name)
                self.groups_joined.append("tickets_staff_all")
            else:
                for did in await _dept_ids_for(user.id):
                    dg = f"tickets_dept_{did}"
                    await self.channel_layer.group_add(dg, self.channel_name)
                    self.groups_joined.append(dg)
        await self.accept()
        await self.send_json({"type": "connected", "channel": "notify"})

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
            tid = content.get("ticket_id")
            if not tid:
                return
            # Owner or staff may subscribe
            owns = await _user_owns_ticket(self.user.id, int(tid))
            if not owns and not (self.user.is_staff or self.user.is_superuser):
                return
            g = f"tickets_ticket_{tid}"
            if g not in self.groups_joined:
                await self.channel_layer.group_add(g, self.channel_name)
                self.groups_joined.append(g)
            await self.send_json({"type": "subscribed", "ticket_id": tid})
            return
        if t == "unsubscribe_ticket":
            tid = content.get("ticket_id")
            g = f"tickets_ticket_{tid}"
            if g in self.groups_joined:
                await self.channel_layer.group_discard(g, self.channel_name)
                self.groups_joined.remove(g)

    async def ticket_event(self, event):
        await self.send_json(event.get("data") or {})


def broadcast_ticket_event(event_type: str, ticket, extra=None):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
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
        "username": None,
    }
    try:
        user = getattr(ticket, "user", None)
        if user is not None:
            payload["username"] = getattr(user, "username", None)
    except Exception:
        pass
    if extra:
        for k in ("message_id", "is_staff_reply", "author_id", "reader_id", "marked", "is_staff", "preview"):
            if k in extra:
                payload[k] = extra[k]

    message = {"type": "ticket.event", "data": payload}
    async_to_sync(layer.group_send)("tickets_staff_all", message)
    if getattr(ticket, "department_id", None):
        async_to_sync(layer.group_send)(f"tickets_dept_{ticket.department_id}", message)
    if getattr(ticket, "user_id", None):
        async_to_sync(layer.group_send)(f"tickets_user_{ticket.user_id}", message)
    async_to_sync(layer.group_send)(f"tickets_ticket_{ticket.id}", message)
