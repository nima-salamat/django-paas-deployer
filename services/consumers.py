import asyncio
import shlex
import urllib.parse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .models import Service
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound as DockerNotFound


User = get_user_model()


class ServiceLogsConsumer(AsyncJsonWebsocketConsumer):
    """
    Runtime log WebSocket: authz + Channels subscription + cursor replay.

    Does NOT follow Docker. Collector is the only Docker log reader.
    """

    async def connect(self):
        query = self.scope.get("query_string", b"").decode("utf-8")
        params = urllib.parse.parse_qs(query)
        token_list = params.get("token") or []
        access_token = token_list[0] if token_list else None
        cursor = (params.get("cursor") or [None])[0]

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

        allowed = await database_sync_to_async(self._authorize)(self.user, self.service_id)
        if not allowed:
            await self.close(code=4003)
            return

        from logs.realtime import group_name

        self.log_group = group_name(self.service_id)
        await self.channel_layer.group_add(self.log_group, self.channel_name)
        await self.accept()
        if cursor:
            await self._replay_from_cursor(cursor)
        else:
            await self._send_latest_window()

    def _authorize(self, user, service_id):
        from services.models import Service
        from services.api.sharing import user_can_access_service

        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return False
        if str(service.user_id) == str(user.id):
            return True
        ok, _ = user_can_access_service(service, user, action="can_view_logs")
        return bool(ok)

    async def disconnect(self, code):
        if getattr(self, "log_group", None) and self.channel_layer:
            try:
                await self.channel_layer.group_discard(self.log_group, self.channel_name)
            except Exception:
                pass

    async def _send_latest_window(self):
        try:
            from logs.query import query_logs

            data = await database_sync_to_async(
                lambda: query_logs(self.service_id, limit=100)
            )()
            await self.send_json(
                {
                    "type": "logs.snapshot",
                    "events": data.get("events") or [],
                    "next_cursor": data.get("next_cursor"),
                    "prev_cursor": data.get("prev_cursor"),
                }
            )
        except Exception:
            await self.send_json({"type": "logs.snapshot", "events": []})

    async def _replay_from_cursor(self, cursor: str):
        try:
            from logs.query import query_logs
            from logs.exceptions import ExpiredCursorError

            def _q():
                return query_logs(self.service_id, cursor=cursor, direction="newer", limit=200)

            try:
                data = await database_sync_to_async(_q)()
            except ExpiredCursorError:
                await self.send_json({"type": "logs.gap", "detail": "cursor expired"})
                data = await database_sync_to_async(
                    lambda: query_logs(self.service_id, limit=100)
                )()
                await self.send_json(
                    {
                        "type": "logs.snapshot",
                        "events": data.get("events") or [],
                        "gap": True,
                    }
                )
                return
            for ev in data.get("events") or []:
                await self.send_json({"type": "logs.line", "event": ev})
        except Exception:
            await self.send_json({"type": "logs.error", "detail": "replay failed"})

    async def receive_json(self, content, **kwargs):
        """Client may request replay: {"action": "replay", "cursor": "..."}."""
        if not isinstance(content, dict):
            return
        if content.get("action") == "replay" and content.get("cursor"):
            await self._replay_from_cursor(str(content["cursor"]))

    async def runtime_log_batch(self, event):
        for ev in event.get("events") or []:
            await self.send_json({"type": "logs.line", "event": ev})


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
            name = str(content.get("name") or "").strip().lower()
            # Map UI signals to the matching terminal control bytes.
            control = {
                "ctrl-c": "\x03",  # ETX  — interrupt
                "ctrl-d": "\x04",  # EOT  — EOF
                "ctrl-z": "\x1a",  # SUB  — suspend (often ignored in containers)
                "ctrl-l": "\x0c",  # FF   — form feed / clear
            }.get(name, "")
            if control:
                await self._write_stdin(control)
            return
        if message_type == "resize":
            # Best-effort: store cols/rows for subsequent execs via environment.
            try:
                cols = max(20, min(int(content.get("cols") or 120), 500))
                rows = max(5, min(int(content.get("rows") or 40), 200))
            except (TypeError, ValueError):
                cols, rows = 120, 40
            self.term_cols = cols
            self.term_rows = rows
            await self.send_json({"type": "resize.ack", "cols": cols, "rows": rows})
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
                cols = getattr(self, "term_cols", None) or 120
                rows = getattr(self, "term_rows", None) or 40
                environment["COLUMNS"] = str(cols)
                environment["LINES"] = str(rows)
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
            try:
                from .shell import record_shell_audit
                await database_sync_to_async(record_shell_audit)(
                    service=self.service, user=self.user, session=self.session,
                    action="interactive_start", command=command, cwd=self.session.workdir,
                )
            except Exception:
                pass
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
