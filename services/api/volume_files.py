import functools
import logging
import os
import tarfile
import tempfile
from django.db import transaction
from django.http import FileResponse
from ..models import Service, PrivateNetwork, Volume
from deploy.models import Deploy
from django.shortcuts import get_object_or_404
from ..serializers import (
    PrivateNetworkSerializer,
    ServiceSerializer,
    VolumeSerializer,
    GetServiceSerializer,
)
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, authentication_classes, permission_classes, action
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from deployments.celery.tasks import deploy as start_service
from deployments.celery.tasks import stop as stop_service
from deployments.celery.tasks import run_db_deploy  # DB platforms
from core.global_settings.config import SERVICE_STATUS_CHOICES
from core.utils import make_uuid4
from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.manager.container_manager import Container
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound as DockerNotFound


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------

from .common import *  # noqa

def _docker_volume_names(volume) -> list:
    """Candidate Docker volume names (canonical first)."""
    names = []
    try:
        canonical = volume.get_docker_volume_name()
        if canonical:
            names.append(canonical)
    except Exception:
        pass
    if volume.name and volume.name not in names:
        names.append(volume.name)
    # legacy patterns sometimes used
    try:
        short = f"vol-{volume.id.hex[:8]}-{volume.name}"
        if short not in names:
            names.append(short)
    except Exception:
        pass
    return names


def _get_docker_volume(volume):
    """Resolve the real Docker volume object for a Django Volume row."""
    client = Client()()
    last_err = None
    for name in _docker_volume_names(volume):
        try:
            return client.volumes.get(name), name
        except DockerNotFound as exc:
            last_err = exc
        except Exception as exc:
            last_err = exc
            logger.warning("volumes.get(%s) failed: %s", name, exc)
    if last_err:
        raise last_err
    raise DockerNotFound(f"Volume not found for {volume.name}")


def _get_volume_mountpoint(volume):
    """
    Return host mountpoint if readable; otherwise None.
    Prefer helper-container path when mountpoint is not accessible
    (typical when API runs inside a container).
    """
    docker_vol, docker_name = _get_docker_volume(volume)
    mountpoint = (docker_vol.attrs or {}).get("Mountpoint")
    if mountpoint and os.path.isdir(mountpoint) and os.access(mountpoint, os.R_OK):
        return mountpoint, docker_name
    return None, docker_name


def _list_via_helper_container(docker_name: str):
    """List volume files via short-lived alpine container.

    Emits one JSON object per line (NDJSON) so parsing cannot mix fields:
      {"path":"dir/file.py","type":"file","size":123}
    """
    client = Client()()
    # Pure busybox/ash — no -printf, no python
    script = r"""
set +e
cd /data || exit 1
tmp=/tmp/vol_list.txt
: > "$tmp"
find . -mindepth 1 2>/dev/null | sort | while IFS= read -r p; do
  [ -z "$p" ] && continue
  rel="${p#./}"
  [ -z "$rel" ] && continue
  # escape for JSON string
  esc=$(printf '%s' "$rel" | sed 's/\\/\\\\/g; s/"/\\"/g')
  if [ -d "$p" ]; then
    printf '{"path":"%s","type":"directory","size":0}\n' "$esc" >> "$tmp"
  elif [ -f "$p" ] || [ -L "$p" ]; then
    sz=$(wc -c < "$p" 2>/dev/null | tr -d ' \n')
    case "$sz" in ''|*[!0-9]*) sz=0 ;; esac
    printf '{"path":"%s","type":"file","size":%s}\n' "$esc" "$sz" >> "$tmp"
  fi
done
cat "$tmp"
"""
    container = None
    try:
        container = client.containers.run(
            "alpine:3.20",
            command=["sh", "-c", script],
            volumes={docker_name: {"bind": "/data", "mode": "ro"}},
            detach=True,
            remove=False,
            network_mode="none",
            mem_limit="96m",
        )
        result = container.wait(timeout=90)
        raw = container.logs(stdout=True, stderr=False) or b""
        err = container.logs(stdout=False, stderr=True) or b""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        status_code = result.get("StatusCode", 1) if isinstance(result, dict) else 1

        import json as _json

        files = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Prefer NDJSON
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = _json.loads(line)
                    p = str(obj.get("path") or "").strip().lstrip("/").replace("\\", "/")
                    if not p or p in (".", "/"):
                        continue
                    t = str(obj.get("type") or "file").lower()
                    if t in ("d", "dir", "directory"):
                        t = "directory"
                    else:
                        t = "file"
                    try:
                        sz = int(obj.get("size") or 0)
                    except Exception:
                        sz = 0
                    files.append(
                        {
                            "path": p,
                            "type": t,
                            "size": 0 if t == "directory" else max(0, sz),
                            "modified_at": None,
                        }
                    )
                    continue
                except Exception:
                    pass
            # Legacy fallbacks: type|size|path  OR  type\tsize\tmtime\tpath
            if "|" in line and line.count("|") >= 2:
                a, b, c = line.split("|", 2)
                t = a.strip().lower()
                t = "directory" if t.startswith("d") else "file"
                try:
                    sz = int(b)
                except Exception:
                    sz = 0
                p = c.strip().lstrip("/").replace("\\", "/")
                if p:
                    files.append({"path": p, "type": t, "size": 0 if t == "directory" else sz, "modified_at": None})
                continue
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 4:
                    y, size_s, _mtime, p = parts[0], parts[1], parts[2], parts[3]
                elif len(parts) == 3:
                    y, size_s, p = parts[0], parts[1], parts[2]
                else:
                    continue
                p = (p or "").strip().lstrip("/").replace("\\", "/")
                if not p:
                    continue
                t = "directory" if str(y).lower().startswith("d") else "file"
                # handle odd "0\t0\tpath" directory lines from old scripts
                if str(y).strip() == "0":
                    t = "directory"
                    size_s = "0"
                try:
                    sz = int(float(size_s))
                except Exception:
                    sz = 0
                files.append({"path": p, "type": t, "size": 0 if t == "directory" else sz, "modified_at": None})
                continue

        if status_code not in (0, None) and not files:
            raise RuntimeError((err or raw).strip() or f"helper container exit {status_code}")
        return files
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
            try:
                # double-ensure by id if object stale
                cid = getattr(container, "id", None)
                if cid:
                    Client()().containers.get(cid).remove(force=True)
            except Exception:
                pass


def _list_volume_files(root_path):
    files = []
    for base, dirs, filenames in os.walk(root_path):
        rel_base = os.path.relpath(base, root_path)
        if rel_base == ".":
            rel_base = ""
        for dirname in dirs:
            path = os.path.join(rel_base, dirname).replace("\\", "/")
            full = os.path.join(base, dirname)
            try:
                stats = os.stat(full)
                mtime = stats.st_mtime
            except Exception:
                mtime = 0
            files.append(
                {
                    "path": path,
                    "type": "directory",
                    "size": 0,
                    "modified_at": mtime,
                }
            )
        for filename in filenames:
            path = os.path.join(rel_base, filename).replace("\\", "/")
            full = os.path.join(base, filename)
            try:
                stats = os.stat(full)
                size = stats.st_size
                mtime = stats.st_mtime
            except Exception:
                size, mtime = 0, 0
            files.append(
                {
                    "path": path,
                    "type": "file",
                    "size": size,
                    "modified_at": mtime,
                }
            )
    return files


def _archive_via_helper_container(docker_name: str, archive_name: str):
    """Create tar.gz of volume contents via helper container; return host temp path."""
    client = Client()()
    temp_file = tempfile.NamedTemporaryFile(
        prefix="volume_archive_", suffix=".tar.gz", delete=False
    )
    temp_path = temp_file.name
    temp_file.close()

    container = None
    try:
        # Write archive inside the container then copy out
        container = client.containers.run(
            "alpine:3.20",
            command=[
                "sh",
                "-c",
                "cd /data && tar -czf /tmp/vol.tgz . && cat /tmp/vol.tgz",
            ],
            volumes={docker_name: {"bind": "/data", "mode": "ro"}},
            detach=True,
            remove=False,
            network_mode="none",
            mem_limit="256m",
        )
        result = container.wait(timeout=300)
        status_code = result.get("StatusCode", 1) if isinstance(result, dict) else 1
        raw = container.logs(stdout=True, stderr=False) or b""
        if status_code not in (0, None):
            err = container.logs(stdout=False, stderr=True) or b""
            raise RuntimeError(
                err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
            )
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        with open(temp_path, "wb") as fh:
            fh.write(raw)
        return temp_path
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
            try:
                cid = getattr(container, "id", None)
                if cid:
                    Client()().containers.get(cid).remove(force=True)
            except Exception:
                pass


def _create_volume_archive(root_path, archive_name):
    temp_file = tempfile.NamedTemporaryFile(
        prefix="volume_archive_", suffix=".tar.gz", delete=False
    )
    temp_file.close()
    with tarfile.open(temp_file.name, mode="w:gz") as tar:
        tar.add(root_path, arcname=".")
    return temp_file.name


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def volume_files_apiview(request, pk):
    volume = get_object_or_404(Volume.objects.filter(user=request.user), pk=pk)
    try:
        mountpoint, docker_name = _get_volume_mountpoint(volume)
        if mountpoint:
            files = _list_volume_files(mountpoint)
        else:
            files = _list_via_helper_container(docker_name)
        # sort: directories first, then path
        files.sort(key=lambda x: (0 if x.get("type") == "directory" else 1, x.get("path") or ""))
        return Response(
            {
                "result": "success",
                "docker_name": docker_name,
                "files": files,
                "count": len(files),
            },
            status=status.HTTP_200_OK,
        )
    except DockerNotFound:
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Docker volume not found. It may not have been created yet — "
                    "start/rebuild the service once so the volume is provisioned."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.exception("volume_files failed for %s", pk)
        return Response(
            {
                "result": "error",
                "detail": _("Unable to list volume files: %(err)s")
                % {"err": str(exc)[:300]},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def volume_download_apiview(request, pk):
    volume = get_object_or_404(Volume.objects.filter(user=request.user), pk=pk)
    archive_path = None
    try:
        mountpoint, docker_name = _get_volume_mountpoint(volume)
        if mountpoint:
            archive_path = _create_volume_archive(mountpoint, volume.name)
        else:
            archive_path = _archive_via_helper_container(docker_name, volume.name)

        response = FileResponse(
            open(archive_path, "rb"),
            as_attachment=True,
            filename=f"{volume.name}.tar.gz",
        )
        response["Content-Length"] = os.path.getsize(archive_path)
        response["Content-Type"] = "application/gzip"

        # Best-effort cleanup after response is closed
        def _cleanup(path=archive_path):
            try:
                os.unlink(path)
            except Exception:
                pass

        try:
            response._resource_closers.append(lambda: _cleanup())  # type: ignore[attr-defined]
        except Exception:
            pass
        return response
    except DockerNotFound:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Docker volume not found. Start/rebuild the service to provision it."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        logger.exception("volume_download failed for %s", pk)
        return Response(
            {
                "result": "error",
                "detail": _("Unable to create volume archive: %(err)s")
                % {"err": str(exc)[:300]},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )




@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def purge_service_runtime_apiview(request):
    """
    Force-remove Docker container + image for a service so volumes can be
    attached / detached / deleted. Body: { "service_id": "<uuid>" }
    """
    service_id = request.data.get("service_id", "")
    if not service_id:
        return Response(
            {"result": "error", "detail": _("service_id is required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        service = _get_service_for_user(request, service_id)
        service = Service.objects.select_related("plan").get(pk=service.pk)
    except Service.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Service not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )

    status_now = str(getattr(service, "status", "") or "").lower()
    if status_now in ("queued", "deploying", "stopping"):
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Service is busy (%(s)s). Wait until it is stopped."
                )
                % {"s": status_now},
            },
            status=status.HTTP_409_CONFLICT,
        )

    report = _purge_service_runtime(service)
    ok = report.get("container") in ("removed", "absent") and not any(
        str(i.get("result", "")).startswith("error") for i in report.get("images", [])
    )
    return Response(
        {
            "result": "success" if ok else "partial",
            "detail": _("Container and image cleanup finished."),
            "report": report,
            "mutable": _service_is_mutable(Service.objects.get(pk=service.pk))[0],
        },
        status=status.HTTP_200_OK,
    )


