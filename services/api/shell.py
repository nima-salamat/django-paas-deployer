from django.core.exceptions import ValidationError
import posixpath
from django.http import Http404
from django.utils import timezone
from services.models import Service
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError

from .common import _get_service_for_user_or_share
from ..shell import authenticate_session, close_session, create_session, terminate_active_session, execute_command, command_catalog, _platform_for_service, _resolve_container, _safe_workdir, path_access


def _resolve(request, service_id, action="can_shell"):
    """Resolve owner/shared service and enforce the action permission.

    Every shell endpoint calls this helper, so hiding the UI is never the
    authorization boundary. Owners pass automatically; shared recipients
    require the explicit ``can_shell`` share permission.
    """
    return _get_service_for_user_or_share(
        request, service_id, action=action, for_update=False
    )[0]

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_info_apiview(request, service_id):
    """Return shell capability metadata for Service Detail UI.

    The permission is evaluated server-side; clients must still call the
    session endpoint, which re-checks authorization.
    """
    try:
        service, share = _get_service_for_user_or_share(
            request, service_id, action="can_view", for_update=False
        )
        from services.api.sharing import user_can_access_service
        is_owner = str(service.user_id) == str(request.user.id)
        allowed, _ = user_can_access_service(
            service, request.user, action="can_shell"
        )
        can_replace = is_owner or bool(user_can_access_service(service, request.user, action="can_shell_replace")[0])
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "enabled": bool(allowed),
            "is_owner": is_owner,
            "permission": "can_shell",
            "can_replace_session": bool(can_replace),
            "shared": share is not None,
            "menu": {
                "id": "shell",
                "label": "Shell",
                "visible": bool(allowed),
                "enabled": bool(allowed),
                "route": f"/services/{service.pk}/shell/",
            },
        })
    except PermissionError as exc:
        return Response({"result": "error", "detail": str(exc)}, status=403)
    except (Service.DoesNotExist, Http404):
        return Response({"result": "error", "detail": "Service not found."}, status=404)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_catalog_apiview(request, service_id):
    """Return the restricted, platform-aware command catalog for the shell UI."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        platform = _platform_for_service(service)
        return Response({
            "result": "success",
            "platform": platform,
            "commands": command_catalog(platform),
            "interactive": {
                "supported": True,
                "transport": "websocket",
                "endpoint": f"/ws/services/shell/{service.pk}/",
                "stdin": True,
                "pty": True,
                "note": "Commands marked interactive may pause and request stdin without terminating the process.",
            },
            "policy": {
                "shell_operators": False,
                "arbitrary_php_scripts": False,
                "arbitrary_python_eval": False,
                "destructive_commands_require_confirmation": True,
                "custom_commands_require_admin_policy": True,
            },
        })
    except PermissionError as exc:
        return Response({"result":"error","detail":str(exc)}, status=403)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_create_apiview(request, service_id):
    try:
        service = _resolve(request, service_id, action="can_shell")
        session, token = create_session(service, request.user, request.data.get("workdir"))
        return Response({"result":"success","session_id":str(session.id),"token":token,"platform":session.platform,"cwd":session.workdir,"expires_at":session.expires_at}, status=201)
    except ValidationError as exc:
        from services.models import ShellSession
        from services.api.sharing import user_can_access_service
        if "already has an active shell session" in str(exc):
            active = ShellSession.objects.filter(
                service=service, status=ShellSession.Status.ACTIVE, expires_at__gt=timezone.now()
            ).select_related("user").first()
            is_owner = str(service.user_id) == str(request.user.id)
            can_replace = is_owner or bool(user_can_access_service(service, request.user, action="can_shell_replace")[0])
            return Response({
                "result": "error",
                "code": "SHELL_SESSION_ACTIVE",
                "detail": (exc.messages[0] if getattr(exc, "messages", None) else str(exc)),
                "can_replace": bool(can_replace),
                "active_session": {
                    "session_id": str(active.id) if active else None,
                    "user_id": str(active.user_id) if active else None,
                    "username": getattr(active.user, "username", None) if active else None,
                    "expires_at": active.expires_at if active else None,
                },
            }, status=409)
        return Response({"result":"error","detail":str(exc)}, status=409)
    except PermissionError as exc:
        return Response({"result":"error","detail":str(exc)}, status=403)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_replace_apiview(request, service_id):
    """Replace the only active shell session after a privileged confirmation."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        from services.api.sharing import user_can_access_service
        is_owner = str(service.user_id) == str(request.user.id)
        can_replace = is_owner or bool(user_can_access_service(service, request.user, action="can_shell_replace")[0])
        if not can_replace:
            return Response({"result":"error","detail":"You are not allowed to replace another user's shell session."}, status=403)
        if request.data.get("confirm") is not True:
            return Response({"result":"error","detail":"confirm=true is required to replace the active shell session."}, status=400)
        old = terminate_active_session(service, actor=request.user)
        session, token = create_session(service, request.user, request.data.get("workdir"))
        return Response({
            "result":"success",
            "replaced": bool(old),
            "previous_session_id": str(old.id) if old else None,
            "session_id": str(session.id),
            "token": token,
            "platform": session.platform,
            "cwd": session.workdir,
            "expires_at": session.expires_at,
        }, status=201)
    except PermissionError as exc:
        return Response({"result":"error","detail":str(exc)}, status=403)
    except ValidationError as exc:
        return Response({"result":"error","detail":str(exc)}, status=409)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_command_apiview(request, service_id):
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        result = execute_command(session, request.data.get("command", ""), confirm=bool(request.data.get("confirm", False)))
        return Response({"result":"success", **result}, status=200)
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_close_apiview(request, service_id):
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        close_session(session)
        return Response({"result":"success"})
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_tree_apiview(request, service_id):
    """Return direct workspace entries with effective RO/RW metadata."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        container = _resolve_container(service)
        result = container.exec_run(["ls", "-1Ap", "--", session.workdir], stdout=True, stderr=True, demux=True, tty=False)
        out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
        if int(result.exit_code or 0) != 0:
            raise DjangoValidationError((err or b"Unable to read directory.").decode("utf-8", "replace"))
        entries=[]
        access_policy = None
        try:
            from ..shell import _container_mount_policy
            access_policy = _container_mount_policy(container)
        except Exception:
            access_policy = None
        cwd_access = path_access(container, session.workdir, for_create=True, policy=access_policy)
        for raw in (out or b"").decode("utf-8", "replace").splitlines():
            raw=raw.strip()
            if not raw: continue
            directory=raw.endswith("/")
            name=raw[:-1] if directory else raw
            path=_safe_workdir(name, session.workdir)
            access=path_access(container, path, for_create=not directory, policy=access_policy)
            entries.append({
                "name": name,
                "path": path,
                "directory": directory,
                "writable": access["writable"],
                "mode": access["mode"],
                "mount_writable": access.get("mount_writable", access["writable"]),
                "effective_writable": access.get("effective_writable", access["writable"]),
                "read_only_reason": access["reason"] if not access["writable"] else "",
            })
        return Response({
            "result": "success",
            "cwd": session.workdir,
            "cwd_writable": cwd_access["writable"],
            "cwd_mode": cwd_access["mode"],
            "cwd_mount_writable": cwd_access.get("mount_writable", cwd_access["writable"]),
            "cwd_read_only_reason": cwd_access["reason"] if not cwd_access["writable"] else "",
            "entries": entries,
        })
    except (PermissionError, DjangoValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_file_apiview(request, service_id):
    """Read/write a text file inside the restricted work directory without a TTY editor."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        container = _resolve_container(service)
        action = str(request.data.get("action") or "read").lower()
        path = str(request.data.get("path") or "").strip()
        if not path:
            raise ValidationError("path is required")
        safe_path = _safe_workdir(path, session.root_path)
        if action == "create":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root cannot be created or replaced.")
            access = path_access(container, safe_path, for_create=True)
            if not access["writable"]:
                raise DjangoValidationError(f"Path is read-only: {safe_path} ({access['reason']}).")
            parent_probe = container.exec_run(["test", "-d", posixpath.dirname(safe_path) or session.root_path], workdir=session.workdir, stdout=False, stderr=False, tty=False)
            if int(parent_probe.exit_code or 1) != 0:
                raise DjangoValidationError("Parent directory does not exist.")
            result = container.exec_run(["touch", "--", safe_path], workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
            if int(result.exit_code or 0) != 0:
                out, err = result.output if isinstance(result.output, tuple) else (b"", result.output or b"")
                raise DjangoValidationError((err or out or b"Unable to create file.").decode("utf-8", "replace"))
            return Response({"result":"success", "path":safe_path, "action":"create", "content":"", "writable":True, "mode":"rw"})
        if action == "delete":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root cannot be deleted.")
            access = path_access(container, safe_path, for_create=True)
            if not access["writable"]:
                raise DjangoValidationError(f"Path is read-only: {safe_path} ({access['reason']}).")
            type_probe = container.exec_run(["test", "-f", "--", safe_path], workdir=session.workdir, stdout=False, stderr=False, tty=False)
            if int(type_probe.exit_code or 1) != 0:
                raise DjangoValidationError("Only regular files can be deleted from the file editor.")
            result = container.exec_run(["rm", "--", safe_path], workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
            if int(result.exit_code or 0) != 0:
                out, err = result.output if isinstance(result.output, tuple) else (b"", result.output or b"")
                raise DjangoValidationError((err or out or b"Unable to delete file.").decode("utf-8", "replace"))
            return Response({"result":"success", "path":safe_path, "action":"delete"})
        if action == "read":
            result = container.exec_run(["cat", "--", safe_path], workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
            access = path_access(container, safe_path, for_create=False)
            out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
            return Response({"result":"success", "path":safe_path, "exit_code":int(result.exit_code or 0), "content":(out or b"")[:262144].decode("utf-8","replace"), "stderr":(err or b"")[:16384].decode("utf-8","replace"), "writable":access["writable"], "mode":access["mode"], "mount_writable":access.get("mount_writable", access["writable"]), "effective_writable":access.get("effective_writable", access["writable"]), "read_only_reason":access["reason"] if not access["writable"] else ""})
        if action == "write":
            content = request.data.get("content")
            if not isinstance(content, str):
                raise ValidationError("content must be a string")
            if len(content.encode("utf-8")) > 262144:
                raise ValidationError("File is too large for the restricted editor (256 KiB).")
            access = path_access(container, safe_path, for_create=True)
            if not access["writable"]:
                raise DjangoValidationError(f"Path is read-only: {safe_path} ({access['reason']}).")
            import base64
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            # No shell: base64 is used only through argv, and the target path is already validated.
            result = container.exec_run(["base64", "-d", "-o", safe_path], workdir=session.workdir, stdin=True, stdout=True, stderr=True, demux=True, tty=False, socket=True)
            sock = result.output
            sock._sock.sendall((encoded + "\n").encode("ascii"))
            sock._sock.shutdown(1)
            return Response({"result":"success", "path":safe_path, "action":"write", "writable":True, "mode":"rw"})
        raise ValidationError("action must be read or write")
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)
