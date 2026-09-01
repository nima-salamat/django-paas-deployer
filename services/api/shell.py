from django.core.exceptions import ValidationError
from django.http import Http404
from services.models import Service
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError

from .common import _get_service_for_user_or_share
from ..shell import authenticate_session, close_session, create_session, execute_command, command_catalog, _platform_for_service


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
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "enabled": bool(allowed),
            "is_owner": is_owner,
            "permission": "can_shell",
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
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 409)

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
def shell_file_apiview(request, service_id):
    """Read/write a text file inside the restricted work directory without a TTY editor."""
    try:
        service = _resolve(request, service_id, action="can_shell")
        token = request.headers.get("X-Shell-Token") or request.data.get("token")
        session = authenticate_session(service, request.user, token)
        from services.shell import _resolve_container, _safe_workdir
        container = _resolve_container(service)
        action = str(request.data.get("action") or "read").lower()
        path = str(request.data.get("path") or "").strip()
        if not path:
            raise ValidationError("path is required")
        safe_path = _safe_workdir(path, session.root_path)
        if action == "read":
            result = container.exec_run(["cat", "--", safe_path], workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
            out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
            return Response({"result":"success", "path":safe_path, "exit_code":int(result.exit_code or 0), "content":(out or b"")[:262144].decode("utf-8","replace"), "stderr":(err or b"")[:16384].decode("utf-8","replace")})
        if action == "write":
            content = request.data.get("content")
            if not isinstance(content, str):
                raise ValidationError("content must be a string")
            if len(content.encode("utf-8")) > 262144:
                raise ValidationError("File is too large for the restricted editor (256 KiB).")
            import base64
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            # No shell: base64 is used only through argv, and the target path is already validated.
            result = container.exec_run(["base64", "-d", "-o", safe_path], workdir=session.workdir, stdin=True, stdout=True, stderr=True, demux=True, tty=False, socket=True)
            sock = result.output
            sock._sock.sendall((encoded + "\n").encode("ascii"))
            sock._sock.shutdown(1)
            return Response({"result":"success", "path":safe_path, "action":"write"})
        raise ValidationError("action must be read or write")
    except (PermissionError, ValidationError) as exc:
        return Response({"result":"error","detail":str(exc)}, status=403 if isinstance(exc, PermissionError) else 400)
    except Service.DoesNotExist:
        return Response({"result":"error","detail":"Service not found."}, status=404)
