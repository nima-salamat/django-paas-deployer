import urllib.parse
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from deploy.models import Deploy


class DeploymentConsumer(AsyncJsonWebsocketConsumer):
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

        self.user_id = user_id
        self.deploy_id = self.scope["url_route"]["kwargs"].get("deploy_id")
        # Permission check: only owner or superuser can subscribe
        deploy = await database_sync_to_async(get_object_or_404)(Deploy.objects.select_related("service", "service__user"), pk=self.deploy_id)
        if deploy.service.user_id != int(self.user_id):
            # deny unless superuser - we can't easily check superuser status from token here without DB lookup
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = await database_sync_to_async(User.objects.get)(pk=self.user_id)
            if not user.is_superuser:
                await self.close(code=4003)
                return

        self.group_name = f"deploy_{self.deploy_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            pass

    # handler for messages sent from sink (type: deployment.message)
    async def deployment_message(self, event):
        payload = event.get("payload")
        await self.send_json({"type": "deployment.event", "event": payload})
