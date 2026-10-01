from __future__ import annotations

import logging
from collections import deque
import urllib.parse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from deploy.models import Deploy
from auth_users.authentication import get_session_id_from_access_token, resolve_user_from_access_token
from auth_users.session_auth import resolve_session

logger = logging.getLogger(__name__)


class DeploymentConsumer(AsyncJsonWebsocketConsumer):
    """
    Live deployment events for one Deploy row.

    Client connects to:
      ws/deployments/<deploy_id>/?token=<jwt>

    Server pushes:
      {"type": "deployment.event", "event": {stage, message, level, progress, ...}}
    """

    async def connect(self):
        query = self.scope.get("query_string", b"").decode("utf-8")
        params = urllib.parse.parse_qs(query)
        token_list = params.get("token") or []
        access_token = token_list[0] if token_list else None

        if not access_token:
            await self.close(code=4001)
            return

        self.user = await database_sync_to_async(resolve_user_from_access_token)(access_token)
        self.auth_session_id = get_session_id_from_access_token(access_token)
        if self.user is None or not self.auth_session_id:
            await self.close(code=4002)
            return

        self.user_id = int(self.user.id)
        # Outbox delivery is at-least-once. Keep a small per-connection
        # dedupe window so a retried event does not update the UI twice.
        self._seen_event_ids = set()
        self._seen_event_order = deque(maxlen=256)
        # Normalise to string so group name matches sink (deploy_<str(pk)>)
        raw_id = self.scope["url_route"]["kwargs"].get("deploy_id")
        self.deploy_id = str(raw_id) if raw_id is not None else None
        if not self.deploy_id:
            await self.close(code=4004)
            return

        allowed = await self._user_may_subscribe(self.deploy_id, self.user_id)
        if not allowed:
            await self.close(code=4003)
            return

        self.group_name = f"deploy_{self.deploy_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        bootstrap = await self._bootstrap_snapshot()
        await self.send_json(
            {
                "type": "deployment.connected",
                "event": {
                    "deploy_id": self.deploy_id,
                    "message": "Subscribed to deployment events.",
                    **bootstrap,
                },
            }
        )
        logger.info(
            "WS subscribed deploy=%s user=%s group=%s",
            self.deploy_id,
            self.user_id,
            self.group_name,
        )

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception:
                logger.debug("group_discard failed", exc_info=True)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("type") == "ping":
            try:
                await database_sync_to_async(resolve_session)(
                    self.auth_session_id,
                    user_id=self.user.id,
                )
            except Exception:
                await self.close(code=4401)
                return
            await self.send_json({"type": "pong"})
            return

    async def deployment_message(self, event):
        """Channel-layer handler: type = "deployment.message"."""
        payload = event.get("payload") or {}
        event_id = str(payload.get("event_id") or "").strip()
        if event_id:
            if event_id in self._seen_event_ids:
                return
            if len(self._seen_event_order) == self._seen_event_order.maxlen:
                oldest = self._seen_event_order[0]
                self._seen_event_ids.discard(oldest)
            self._seen_event_order.append(event_id)
            self._seen_event_ids.add(event_id)
        try:
            await self.send_json({"type": "deployment.event", "event": payload})
        except Exception:
            logger.exception(
                "Failed to send deployment event to client deploy=%s",
                getattr(self, "deploy_id", None),
            )

    @database_sync_to_async
    def _user_may_subscribe(self, deploy_id, user_id: int) -> bool:
        try:
            deploy = get_object_or_404(
                Deploy.objects.select_related("service", "service__user"),
                pk=deploy_id,
            )
        except Exception:
            return False

        owner_id = getattr(deploy.service, "user_id", None)
        if owner_id is not None and int(owner_id) == int(user_id):
            return True

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            return bool(getattr(user, "is_superuser", False))
        except User.DoesNotExist:
            return False

    @database_sync_to_async
    def _bootstrap_snapshot(self) -> dict:
        """Send current Deploy progress so late subscribers catch up."""
        try:
            deploy = Deploy.objects.only(
                "status", "stage", "progress", "status_message", "error_message"
            ).get(pk=self.deploy_id)
            return {
                "status": getattr(deploy, "status", None),
                "stage": getattr(deploy, "stage", None),
                "progress": getattr(deploy, "progress", None),
                "status_message": getattr(deploy, "status_message", None),
                "error_message": getattr(deploy, "error_message", None) or None,
            }
        except Exception:
            return {}
