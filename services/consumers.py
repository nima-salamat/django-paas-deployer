import asyncio
import urllib.parse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .models import Service
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound as DockerNotFound


User = get_user_model()


class ServiceLogsConsumer(AsyncJsonWebsocketConsumer):
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

        self.user = await database_sync_to_async(User.objects.get)(pk=user_id)
        self.service_id = self.scope["url_route"]["kwargs"].get("service_id")
        self.service = await database_sync_to_async(get_object_or_404)(Service.objects.filter(user=self.user), pk=self.service_id)
        self.container_name = self.service.get_docker_service_name()
        await self.accept()
        self.log_task = asyncio.create_task(self.stream_container_logs())

    async def disconnect(self, code):
        if hasattr(self, "log_task") and not self.log_task.done():
            self.log_task.cancel()
            try:
                await self.log_task
            except asyncio.CancelledError:
                pass

    async def stream_container_logs(self):
        loop = asyncio.get_running_loop()

        def iter_logs():
            client = Client()()
            container = client.containers.get(self.container_name)
            for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True, timestamps=True, tail=50):
                if isinstance(raw, (bytes, bytearray)):
                    yield raw.decode("utf-8", "replace")
                else:
                    yield str(raw)

        try:
            log_iter = iter_logs()
            while True:
                try:
                    line = await loop.run_in_executor(None, lambda: next(log_iter))
                except StopIteration:
                    break
                await self.send_json({"type": "log.line", "line": line})
        except DockerNotFound:
            await self.send_json({"type": "error", "message": "Container not found or has been removed."})
        except Exception as exc:
            await self.send_json({"type": "error", "message": f"Log stream error: {str(exc)}"})
