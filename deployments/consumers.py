from __future__ import annotations

import logging
import urllib.parse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from deploy.models import Deploy

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

        try:
            validated = AccessToken(access_token)
            user_id = validated["user_id"]
        except (InvalidToken, TokenError, KeyError):
            await self.close(code=4002)
            return

        self.user_id = int(user_id)
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

    async def deployment_message(self, event):
        """Channel-layer handler: type = \"deployment.message\"."""
        payload = event.get("payload") or {}
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
