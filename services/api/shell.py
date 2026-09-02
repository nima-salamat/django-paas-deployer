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
from ..shell import authenticate_session, close_session, create_session, terminate_active_session, execute_command, command_catalog, _platform_for_service, _resolve_container, _safe_workdir, path_access, batch_path_writable


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
    """Fast directory listing. Expensive permission metadata is deferred."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        container = _resolve_container(service)
        result = container.exec_run(["ls", "-1Ap", session.workdir], stdout=True, stderr=True, demux=True, tty=False)
        out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
        if int(result.exit_code or 0) != 0:
            raise DjangoValidationError((err or b"Unable to read directory.").decode("utf-8", "replace"))

        from ..shell import _container_mount_policy
        try:
            access_policy = _container_mount_policy(container)
        except Exception:
            access_policy = (False, [])
        root_ro, mounts = access_policy
        def mount_mode(path):
            for mount_path, rw in mounts:
                if path == mount_path or path.startswith(mount_path.rstrip("/") + "/"):
                    return bool(rw)
            return not root_ro

        entries = []
        for raw in (out or b"").decode("utf-8", "replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            directory = raw.endswith("/")
            name = raw[:-1] if directory else raw
            path = _safe_workdir(name, session.workdir)
            mount_rw = mount_mode(path)
            entries.append({
                "name": name,
                "path": path,
                "directory": directory,
                "mode": "rw" if mount_rw else "ro",
                "mount_writable": mount_rw,
                "writable": mount_rw,
                "effective_writable": None,
                "read_only_reason": "Checking permissions…" if mount_rw else "Read-only filesystem/mount",
            })
        cwd_mount_rw = mount_mode(session.workdir)
        return Response({
            "result": "success",
            "cwd": session.workdir,
            "cwd_writable": None,
            "cwd_mode": "rw" if cwd_mount_rw else "ro",
            "cwd_mount_writable": cwd_mount_rw,
            "cwd_read_only_reason": "Checking permissions…" if cwd_mount_rw else "Read-only filesystem/mount",
            "metadata_pending": True,
            "entries": entries,
        })
    except (PermissionError, DjangoValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shell_tree_meta_apiview(request, service_id):
    """Batch effective RW metadata after the fast tree has rendered."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        container = _resolve_container(service)
        paths = request.data.get("paths") or []
        paths = [str(p) for p in paths if p]
        from ..shell import _container_mount_policy
        try:
            policy = _container_mount_policy(container)
        except Exception:
            policy = None
        access = batch_path_writable(container, paths + [session.workdir], policy=policy)
        cwd_key = posixpath.normpath(session.workdir)
        cwd_user_writable = bool(access.get(cwd_key, False))
        cwd_mount_writable = True
        for mount_path, rw in sorted(policy[1], key=lambda x: len(x[0]), reverse=True):
            if cwd_key == mount_path or cwd_key.startswith(mount_path.rstrip('/') + '/'):
                cwd_mount_writable = bool(rw); break
        if policy[0] and cwd_key not in {m[0] for m in policy[1]}:
            cwd_mount_writable = False
        result = []
        for path in paths:
            safe = _safe_workdir(path, session.root_path)
            key = posixpath.normpath(safe)
            mount_writable = True
            for mount_path, rw in sorted(policy[1], key=lambda x: len(x[0]), reverse=True):
                if key == mount_path or key.startswith(mount_path.rstrip('/') + '/'):
                    mount_writable = bool(rw); break
            if policy[0] and not any(key == m[0] or key.startswith(m[0].rstrip('/') + '/') for m in policy[1]):
                mount_writable = False
            managed = bool(mount_writable)
            user_writable = bool(access.get(key, False))
            result.append({
                "path": safe,
                "effective_writable": user_writable,
                "managed_writable": managed,
                "mount_writable": mount_writable,
                "writable": bool(user_writable or managed),
                "mode": "rw" if mount_writable else "ro",
                "read_only_reason": "" if (user_writable or managed) else ("Read-only Docker mount" if not mount_writable else "Service user cannot write this path")
            })
        return Response({"result":"success", "cwd":session.workdir, "cwd_writable":bool(cwd_user_writable or (cwd_mount_writable and _mode_has_write_bit(container, session.workdir))), "cwd_mount_writable":cwd_mount_writable, "entries":result})
    except (PermissionError, DjangoValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)


def _runtime_identity(container):
    """Return the effective uid/gid used by the running service process."""
    try:
        result = container.exec_run(["id", "-u"], stdout=True, stderr=False, tty=False)
        uid = (result.output or b"").decode("utf-8", "replace").strip()
        result = container.exec_run(["id", "-g"], stdout=True, stderr=False, tty=False)
        gid = (result.output or b"").decode("utf-8", "replace").strip()
        if uid.isdigit() and gid.isdigit():
            return uid, gid
    except Exception:
        pass
    return None, None


def _file_manager_exec(container, argv, *, workdir, stdout=True, stderr=True, allow_root=True):
    """Run a backend-owned file operation with a safe privilege fallback.

    The normal attempt always uses the service runtime user. For mounted project
    files, the restricted file-manager may retry as root when necessary; this is
    never exposed as arbitrary shell execution and callers remain responsible for
    checking the Docker mount policy and workspace boundary first.
    """
    attempts = [(None, False)]
    if allow_root:
        attempts.append(("0", True))
    last = None
    for user, privileged in attempts:
        kwargs = {"workdir": workdir, "stdout": stdout, "stderr": stderr, "demux": True, "tty": False}
        if user is not None:
            kwargs["user"] = user
        try:
            result = container.exec_run(argv, **kwargs)
        except Exception as exc:
            last = exc
            continue
        last = result
        if int(result.exit_code if result.exit_code is not None else 1) == 0:
            return result, privileged
    if isinstance(last, Exception):
        raise last
    return last, bool(attempts and attempts[-1][1])


def _reassign_to_runtime_user(container, path: str) -> bool:
    """After a privileged create, make the new node owned by the real runtime user."""
    uid, gid = _runtime_identity(container)
    if uid is None or gid is None or uid == "0":
        return True
    try:
        result = container.exec_run(["chown", f"{uid}:{gid}", path], user="0", stdout=False, stderr=True, tty=False)
        return int(result.exit_code if result.exit_code is not None else 1) == 0
    except Exception:
        return False


def _mode_has_write_bit(container, path: str) -> bool:
    """Return whether the filesystem mode exposes any write bit for an existing path."""
    try:
        result = container.exec_run(["ls", "-ld", path], stdout=True, stderr=False, tty=False)
        raw = result.output if isinstance(result.output, (bytes, bytearray)) else b""
        if int(result.exit_code if result.exit_code is not None else 1) != 0:
            return False
        line = raw.decode("utf-8", "replace").splitlines()[0].strip() if raw else ""
        perms = line.split()[0] if line else ""
        return len(perms) >= 10 and "w" in perms[:10]
    except Exception:
        return False


def _assert_managed_target_safe(container, path: str, root: str, *, allow_missing: bool = False) -> str:
    """Enforce workspace containment, including container-side symlink resolution.

    Non-existent create targets are checked through their parent. Existing targets
    are resolved with realpath/readlink so a symlink cannot redirect an operation
    outside the service workspace.
    """
    safe = _safe_workdir(path, root)
    try:
        _assert_container_path_within(container, safe, root)
        return safe
    except ValidationError:
        if not allow_missing:
            raise
        parent = posixpath.dirname(safe) or root
        _assert_container_path_within(container, parent, root)
        probe = container.exec_run(["ls", "-ld", safe], workdir=parent, stdout=False, stderr=False, tty=False)
        if int(probe.exit_code if probe.exit_code is not None else 1) == 0:
            raise ValidationError(f"Path resolves outside the service workspace: {safe}")
        return safe


def _exec_stdin_checked(container, argv, *, workdir, data: bytes, user=None):
    """Execute a backend-owned stdin command and return a reliable exit code."""
    api = container.client.api
    kwargs = dict(stdout=True, stderr=True, stdin=True, tty=False, demux=False, workdir=workdir)
    if user is not None:
        kwargs["user"] = user
    created = api.exec_create(container.id, cmd=argv, **kwargs)
    exec_id = created["Id"]
    sock = api.exec_start(exec_id, tty=False, socket=True)
    target = getattr(sock, "_sock", sock)
    chunks = []
    try:
        if data:
            target.sendall(data)
        try:
            target.shutdown(1)
        except Exception:
            pass
        while True:
            chunk = target.recv(32768)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    inspect = api.exec_inspect(exec_id)
    return int(inspect.get("ExitCode") if inspect.get("ExitCode") is not None else 1), b"".join(chunks)


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
        if action in {"delete", "rename", "read", "write"}:
            safe_path = _assert_managed_target_safe(container, safe_path, session.root_path)
        elif action in {"create", "create_folder"}:
            safe_path = _assert_managed_target_safe(container, safe_path, session.root_path, allow_missing=True)
        if action == "create":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root cannot be created or replaced.")
            from ..shell import _container_mount_policy
            try:
                root_ro, mounts = _container_mount_policy(container)
            except Exception:
                root_ro, mounts = False, []
            mount_rw = (not root_ro)
            for mount_path, rw in sorted(mounts, key=lambda x: len(x[0]), reverse=True):
                if safe_path == mount_path or safe_path.startswith(mount_path.rstrip("/") + "/"):
                    mount_rw = bool(rw)
                    break
            if not mount_rw:
                raise DjangoValidationError(f"The target is on a read-only Docker mount: {safe_path}.")
            parent = posixpath.dirname(safe_path) or session.root_path
            name = posixpath.basename(safe_path)
            result, privileged = _file_manager_exec(container, ["touch", name], workdir=parent)
            if result is None or int(result.exit_code if result.exit_code is not None else 1) != 0:
                out, err = result.output if result is not None and isinstance(result.output, tuple) else ((result.output if result is not None else b"") or b"", b"")
                detail = (err or out or b"permission denied").decode("utf-8", "replace").strip()
                raise DjangoValidationError(f"Unable to create file: {detail}")
            if privileged:
                _reassign_to_runtime_user(container, safe_path)
            return Response({"result":"success", "path":safe_path, "action":"create", "content":"", "writable":True, "mode":"rw", "mount_writable":True, "effective_writable":True, "used_privileged_file_manager": privileged})
        if action == "create_folder":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root already exists.")
            from ..shell import _container_mount_policy
            try:
                root_ro, mounts = _container_mount_policy(container)
            except Exception:
                root_ro, mounts = False, []
            mount_rw = not root_ro
            for mount_path, rw in sorted(mounts, key=lambda x: len(x[0]), reverse=True):
                if safe_path == mount_path or safe_path.startswith(mount_path.rstrip("/") + "/"):
                    mount_rw = bool(rw)
                    break
            if not mount_rw:
                raise DjangoValidationError(f"The target is on a read-only Docker mount: {safe_path}.")
            parent = posixpath.dirname(safe_path) or session.root_path
            name = posixpath.basename(safe_path)
            result, privileged = _file_manager_exec(container, ["mkdir", name], workdir=parent)
            if result is None or int(result.exit_code if result.exit_code is not None else 1) != 0:
                out, err = result.output if result is not None and isinstance(result.output, tuple) else ((result.output if result is not None else b"") or b"", b"")
                detail = (err or out or b"permission denied").decode("utf-8", "replace").strip()
                raise DjangoValidationError(f"Unable to create folder: {detail}")
            if privileged:
                _reassign_to_runtime_user(container, safe_path)
            return Response({"result":"success", "path":safe_path, "action":"create_folder", "writable":True, "mode":"rw", "mount_writable":True, "effective_writable":True, "used_privileged_file_manager": privileged})
        if action == "delete":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root cannot be deleted.")
            # Deletion is controlled by the parent directory's write permission,
            # not by the target file's own write bit. Do not reject here based on
            # the runtime user's permission probe because the restricted file
            # manager below may perform the single, backend-owned unlink/rmdir
            # operation with its privileged fallback (and only inside workspace).
            from ..shell import _container_mount_policy
            try:
                root_ro, mounts = _container_mount_policy(container)
            except Exception:
                root_ro, mounts = False, []
            mount_rw = not root_ro
            for mount_path, rw in sorted(mounts, key=lambda x: len(x[0]), reverse=True):
                if safe_path == mount_path or safe_path.startswith(mount_path.rstrip("/") + "/"):
                    mount_rw = bool(rw)
                    break
            if not mount_rw:
                raise DjangoValidationError(f"The target is on a read-only Docker mount: {safe_path}.")
            # Delete files with rm. Directories use rmdir only, so a context-menu
            # delete can never recursively erase a project by accident.
            type_probe = container.exec_run(["ls", "-ld", safe_path], workdir=session.workdir, stdout=False, stderr=False, tty=False)
            if int(type_probe.exit_code if type_probe.exit_code is not None else 1) != 0:
                raise DjangoValidationError("Path does not exist or is not accessible.")
            kind_probe = container.exec_run(["sh", "-c", 'if [ -d "$1" ]; then printf dir; elif [ -f "$1" ]; then printf file; else printf other; fi', "kind", safe_path], workdir=session.workdir, stdout=True, stderr=False, tty=False)
            kind = (kind_probe.output or b"").decode("utf-8", "replace").strip() if isinstance(kind_probe.output, (bytes, bytearray)) else "other"
            cmd = ["rmdir", safe_path] if kind == "dir" else ["rm", safe_path]
            result, privileged = _file_manager_exec(container, cmd, workdir=session.workdir)
            if result is None or int(result.exit_code if result.exit_code is not None else 1) != 0:
                out, err = result.output if result is not None and isinstance(result.output, tuple) else ((result.output if result is not None else b"") or b"", b"")
                detail = (err or out or b"Unable to delete path.").decode("utf-8", "replace").strip()
                raise DjangoValidationError(detail)
            return Response({"result":"success", "path":safe_path, "action":"delete", "kind":kind, "used_privileged_file_manager": privileged})
        if action == "rename":
            if safe_path == session.root_path:
                raise DjangoValidationError("The workspace root cannot be renamed.")
            new_name = str(request.data.get("new_name") or "").strip()
            if not new_name or new_name in {".", ".."} or "/" in new_name or "\\" in new_name or "\x00" in new_name:
                raise DjangoValidationError("new_name must be a single file or directory name.")
            parent = posixpath.dirname(safe_path) or session.root_path
            new_path = _safe_workdir(posixpath.join(parent, new_name), session.root_path)
            access = path_access(container, safe_path, for_create=True)
            if not access.get("mount_writable", False):
                raise DjangoValidationError(f"The target is on a read-only Docker mount: {safe_path}.")
            result, privileged = _file_manager_exec(container, ["mv", safe_path, new_path], workdir=parent)
            if result is None or int(result.exit_code if result.exit_code is not None else 1) != 0:
                out, err = result.output if result is not None and isinstance(result.output, tuple) else ((result.output if result is not None else b"") or b"", b"")
                detail = (err or out or b"Unable to rename path.").decode("utf-8", "replace").strip()
                raise DjangoValidationError(detail)
            return Response({"result":"success", "path":safe_path, "new_path":new_path, "action":"rename", "used_privileged_file_manager": privileged})
        if action == "read":
            result = container.exec_run(["cat", "--", safe_path], workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
            access = path_access(container, safe_path, for_create=False)
            out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
            mount_rw = bool(access.get("mount_writable", False))
            user_writable = bool(access.get("writable", False))
            # The restricted backend-owned file manager is allowed to perform
            # file mutations inside an RW workspace even when the service UID
            # itself is not the owner. Therefore editor capability is based on
            # the mount policy plus the managed file-manager capability, while
            # effective_writable remains the service-user capability.
            managed_writable = bool(mount_rw)
            editor_writable = bool(mount_rw)
            reason = "" if editor_writable else "Read-only Docker mount"
            return Response({"result":"success", "path":safe_path, "exit_code":int(result.exit_code or 0), "content":(out or b"")[:262144].decode("utf-8","replace"), "stderr":(err or b"")[:16384].decode("utf-8","replace"), "writable":editor_writable, "mode":access["mode"], "mount_writable":mount_rw, "effective_writable":user_writable, "managed_writable":managed_writable, "read_only_reason":reason})
        if action == "write":
            content = request.data.get("content")
            if not isinstance(content, str):
                raise ValidationError("content must be a string")
            encoded_content = content.encode("utf-8")
            if len(encoded_content) > 262144:
                raise ValidationError("File is too large for the restricted editor (256 KiB).")
            access = path_access(container, safe_path, for_create=False)
            if not access.get("mount_writable", False):
                raise DjangoValidationError(f"The target is on a read-only Docker mount: {safe_path}.")
            import base64
            encoded = base64.b64encode(encoded_content) + b"\n"
            last_detail = "permission denied"
            for exec_user in (None, "0"):
                try:
                    code, output = _exec_stdin_checked(
                        container,
                        ["/bin/sh", "-c", 'base64 -d > "$1"', "writer", safe_path],
                        workdir=session.workdir, data=encoded, user=exec_user,
                    )
                    if code == 0:
                        return Response({"result":"success", "path":safe_path, "action":"write", "writable":True, "mode":"rw", "mount_writable":True, "effective_writable":bool(access.get("effective_writable")), "managed_writable":True, "used_privileged_file_manager":exec_user == "0"})
                    last_detail = output.decode("utf-8", "replace").strip() or last_detail
                except Exception as exc:
                    last_detail = str(exc) or last_detail
            raise DjangoValidationError(f"Unable to save file: {last_detail}")
        raise ValidationError("action must be read or write")
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","code":"SHELL_FILE_VALIDATION","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","code":"SERVICE_NOT_FOUND","detail":"Service not found."}, status=404)
    except Exception as exc:
        # Do not leak Docker internals and do not turn ordinary filesystem/runtime
        # failures into an opaque HTTP 500. The restricted API returns a structured
        # operational error so the terminal can show the exact action that failed.
        detail = str(exc).strip() or "File operation failed."
        return Response({"result":"error","code":"SHELL_FILE_OPERATION_FAILED","detail":detail}, status=400)
