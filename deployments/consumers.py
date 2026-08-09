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

    # ---------------------------------------------------------------------
    # Stream container logs over WebSocket.
    #
    # IMPORTANT — TTY handling:
    #
    # DB containers are now created with ``tty=True`` + ``stdin_open=True``
    # to work around the MySQL 8.0.46 ``tcgetpgrp()`` ioctl bug (error
    # MY-011065 "Inappropriate ioctl for device"). See
    # deployments/core/db_deployer.py for the full rationale.
    #
    # Side effect of ``tty=True``: Docker's log stream changes format.
    #
    #   * Non-TTY containers: Docker wraps each stdout/stderr frame in an
    #     8-byte header (stream type + length). The Python docker client
    #     parses these headers and yields one chunk per frame — typically
    #     one chunk per write() call, which is usually one line.
    #
    #   * TTY containers: Docker sends a raw byte stream with NO framing.
    #     The Python docker client yields whatever the socket recv()
    #     returns — which can be a single byte, a partial line, multiple
    #     lines, or anything in between. If the consumer sends each chunk
    #     as a separate WebSocket message, the frontend renders each byte
    #     on its own line (the "character-by-character" bug).
    #
    # Fix: buffer incoming bytes and emit a WebSocket message only when
    # we hit a newline (``\r\n`` or ``\n``). The buffer is per-stream so
    # a partial line at the end of one recv() gets prepended to the next.
    #
    # We also detect the container's TTY mode at connect time and use a
    # different code path for each mode, so non-TTY containers (app
    # deploys) keep the original fast path with no buffering overhead.
    # ---------------------------------------------------------------------

    async def stream_container_logs(self):
        loop = asyncio.get_running_loop()

        def get_container():
            client = Client()()
            return client.containers.get(self.container_name)

        try:
            container = await loop.run_in_executor(None, get_container)
        except DockerNotFound:
            await self.send_json({"type": "error", "message": "Container not found or has been removed."})
            return

        # Detect TTY mode by inspecting the container's Config.Tty attribute.
        # This is set at create time and never changes, so we read it once.
        try:
            container.reload()
            is_tty = bool(container.attrs.get("Config", {}).get("Tty", False))
        except Exception:
            is_tty = False

        if is_tty:
            await self._stream_tty_logs(container, loop)
        else:
            await self._stream_framed_logs(container, loop)

    async def _stream_framed_logs(self, container, loop):
        """Fast path for non-TTY containers (app deploys).

        Docker frames each write() in an 8-byte header, so each yielded
        chunk is typically one complete line. No buffering needed.
        """
        def iter_logs():
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

    async def _stream_tty_logs(self, container, loop):
        """Buffered path for TTY-enabled containers (DB deploys with tty=True).

        Docker sends a raw byte stream. We buffer until we hit a newline
        and only then emit a WebSocket message, so the frontend receives
        one complete line per message regardless of how the socket
        fragmented the underlying bytes.
        """
        def iter_bytes():
            # When the container has a TTY, docker-py's logs() yields raw
            # bytes (no framing). We pass demux=False (the default) so we
            # get a single stream — stdout and stderr are already merged
            # by the PTY.
            for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True, timestamps=True, tail=50):
                if isinstance(raw, (bytes, bytearray)):
                    yield bytes(raw)
                else:
                    yield str(raw).encode("utf-8", "replace")

        buf = b""
        try:
            byte_iter = iter_bytes()
            while True:
                try:
                    chunk = await loop.run_in_executor(None, lambda: next(byte_iter))
                except StopIteration:
                    # Flush any remaining buffered bytes (e.g. a partial
                    # line without a trailing newline) before closing.
                    if buf:
                        line = buf.decode("utf-8", "replace").rstrip("\r")
                        if line:
                            await self.send_json({"type": "log.line", "line": line})
                    break

                buf += chunk
                # Split on \n (handles both \n and \r\n — we strip the
                # trailing \r when decoding each line below).
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", "replace").rstrip("\r")
                    if line:
                        await self.send_json({"type": "log.line", "line": line})
        except DockerNotFound:
            await self.send_json({"type": "error", "message": "Container not found or has been removed."})
        except Exception as exc:
            await self.send_json({"type": "error", "message": f"Log stream error: {str(exc)}"})
