import asyncio
import shlex
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


class RestrictedShellConsumer(AsyncJsonWebsocketConsumer):
    """Interactive restricted shell backed by a Docker exec PTY.

    Unlike the legacy POST /shell/command endpoint, this keeps the child
    process and PTY alive across multiple messages so commands such as
    ``python manage.py createsuperuser`` can pause for stdin and continue
    after the browser sends the next line.
    """

    async def connect(self):
        query = self.scope.get("query_string", b"").decode("utf-8")
        params = urllib.parse.parse_qs(query)
        access_token = (params.get("token") or [None])[0]
        shell_token = (params.get("shell_token") or [None])[0]
        service_id = self.scope["url_route"]["kwargs"].get("service_id")
        if not access_token or not shell_token:
            await self.close(code=4001)
            return
        try:
            validated = AccessToken(access_token)
            user_id = validated["user_id"]
            self.user = await database_sync_to_async(User.objects.get)(pk=user_id)
            self.service = await database_sync_to_async(self._get_service)(service_id)
            self.session = await database_sync_to_async(self._authenticate_shell)(shell_token)
        except (InvalidToken, TokenError, KeyError, User.DoesNotExist, Service.DoesNotExist, PermissionError):
            await self.close(code=4003)
            return
        self.exec_socket = None
        self.exec_task = None
        self.exec_id = None
        await self.accept()
        await self.send_json({"type": "ready", "cwd": self.session.workdir, "platform": self.session.platform})

    def _get_service(self, service_id):
        from services.api.sharing import user_can_access_service
        service = Service.objects.filter(pk=service_id).first()
        if not service:
            raise Service.DoesNotExist
        allowed, _ = user_can_access_service(service, self.user, action="can_shell")
        if not allowed:
            raise PermissionError("You are not allowed to use the restricted service shell.")
        return service

    def _authenticate_shell(self, shell_token):
        from .shell import authenticate_session
        return authenticate_session(self.service, self.user, shell_token)

    async def disconnect(self, code):
        if self.exec_task and not self.exec_task.done():
            self.exec_task.cancel()
            try:
                await self.exec_task
            except asyncio.CancelledError:
                pass
        await self._close_exec_socket()

    async def _close_exec_socket(self):
        sock = getattr(self, "exec_socket", None)
        self.exec_socket = None
        if not sock:
            return
        def close_sock():
            try:
                sock.close()
            except Exception:
                pass
        await asyncio.get_running_loop().run_in_executor(None, close_sock)

    async def receive_json(self, content, **kwargs):
        message_type = str(content.get("type") or "").strip().lower()
        if message_type == "command":
            await self._start_command(str(content.get("command") or ""), bool(content.get("confirm", False)))
            return
        if message_type == "stdin":
            await self._write_stdin(str(content.get("data") or ""))
            return
        if message_type == "signal":
            await self._write_stdin("\x03" if content.get("name") == "ctrl-c" else "")
            return
        if message_type == "resize":
            await self.send_json({"type": "resize.unsupported"})
            return
        await self.send_json({"type": "error", "message": "Unsupported shell message."})

    async def _start_command(self, command, confirm):
        from .shell import _reject_shell_syntax, _is_destructive_command, _resolve_container, parse_safe_command, validate_argv_for_container, can_use_advanced_shell
        try:
            if self.exec_socket is not None:
                await self.send_json({"type": "error", "message": "A command is already running. Send input or wait for it to finish."})
                return
            parts = parse_safe_command(command)
            if len(parts) != 1:
                await self.send_json({"type": "error", "message": "Compound commands use the secure command API; interactive PTY accepts one command at a time."})
                return
            argv = parts[0][0]
            container = await database_sync_to_async(_resolve_container)(self.service)
            await database_sync_to_async(validate_argv_for_container)(argv, self.session.platform, self.session.root_path, container, allow_advanced=can_use_advanced_shell(self.service, self.user))
            if _is_destructive_command(argv) and not confirm:
                await self.send_json({"type": "confirm_required", "command": command, "message": "This command changes application state. Confirmation is required."})
                return
            if argv and argv[0] == "cd":
                from .shell import execute_command
                result = await database_sync_to_async(execute_command)(self.session, command, confirm=confirm)
                await self.send_json({"type": "command.output", **result})
                return
            loop = asyncio.get_running_loop()
            def create_exec():
                from services.shell import prepare_interactive_exec_environment
                api = container.client.api
                environment = prepare_interactive_exec_environment(
                    container,
                    platform=getattr(self.session, "platform", None) or "",
                    root_path=getattr(self.session, "root_path", None) or "",
                )
                created = api.exec_create(
                    container.id,
                    cmd=argv,
                    stdout=True,
                    stderr=True,
                    stdin=True,
                    tty=True,
                    workdir=self.session.workdir,
                    environment=environment,
                )
                sock = api.exec_start(created["Id"], tty=True, socket=True)
                return created["Id"], sock
            self.exec_id, self.exec_socket = await loop.run_in_executor(None, create_exec)
            await self.send_json({"type": "process.started", "exec_id": self.exec_id, "cwd": self.session.workdir, "command": command})
            self.exec_task = asyncio.create_task(self._read_exec_output(command))
        except Exception as exc:
            self.exec_id = None
            await self._close_exec_socket()
            await self.send_json({"type": "error", "message": str(exc)})

    async def _read_exec_output(self, command):
        loop = asyncio.get_running_loop()
        sock = self.exec_socket
        try:
            while True:
                chunk = await loop.run_in_executor(None, lambda: self._recv(sock, 32768))
                if not chunk:
                    break
                text = bytes(chunk).decode("utf-8", "replace")
                await self.send_json({"type": "process.output", "data": text})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.send_json({"type": "error", "message": f"Interactive shell stream error: {exc}"})
        finally:
            exit_code = await self._inspect_exit_code()
            try:
                await database_sync_to_async(self._touch_session)()
            except Exception:
                pass
            await self._close_exec_socket()
            self.exec_id = None
            self.exec_task = None
            await self.send_json({"type": "process.exit", "exit_code": exit_code})

    @staticmethod
    def _recv(sock, size):
        target = getattr(sock, "_sock", sock)
        return target.recv(size)

    @staticmethod
    def _send(sock, data):
        target = getattr(sock, "_sock", sock)
        target.sendall(data)

    async def _write_stdin(self, data):
        if not self.exec_socket:
            await self.send_json({"type": "error", "message": "No interactive process is running."})
            return
        loop = asyncio.get_running_loop()
        try:
            payload = data.encode("utf-8")
            await loop.run_in_executor(None, self._send, self.exec_socket, payload)
            await database_sync_to_async(self._touch_session)()
        except Exception as exc:
            await self.send_json({"type": "error", "message": f"Unable to send input: {exc}"})

    def _touch_session(self):
        from .shell import _session_expiry
        now = timezone.now()
        self.session.last_used_at = now
        self.session.expires_at = _session_expiry(now)
        self.session.save(update_fields=["last_used_at", "expires_at"])

    async def _inspect_exit_code(self):
        exec_id = self.exec_id
        if not exec_id:
            return None
        try:
            def inspect_exec():
                try:
                    from deployments.core.manager.client_manager import Client
                    api = Client()().api
                    result = api.exec_inspect(exec_id)
                    return result.get("ExitCode")
                except Exception:
                    return None
            return await asyncio.get_running_loop().run_in_executor(None, inspect_exec)
        except Exception:
            return None
