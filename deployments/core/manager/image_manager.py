from __future__ import annotations

import io
import json
import logging
import os
import re
import tarfile
import tempfile
import traceback
import uuid
from typing import Any, Callable, Optional

import docker
import docker.errors
from docker.errors import BuildError, ImageNotFound

from deployments.core.exceptions import CleanupError, ImageBuildError
from deployments.common.build_slots import BuildSlot
from .client_manager import Client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _setting(name: str, default: Any) -> Any:
    try:
        from django.conf import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _build_default_cpu() -> float:
    try:
        from core import settings_service as svc
        return float(svc.build_max_cpu())
    except Exception:
        return float(_setting("DEPLOY_BUILD_MAX_CPU", os.getenv("DEPLOY_BUILD_MAX_CPU", "1.0")))


def _build_default_ram() -> int:
    try:
        from core import settings_service as svc
        return int(svc.build_max_ram_mb())
    except Exception:
        return int(_setting("DEPLOY_BUILD_MAX_RAM_MB", os.getenv("DEPLOY_BUILD_MAX_RAM_MB", "1024")))


def _build_default_parallelism() -> int:
    try:
        from core import settings_service as svc
        return int(svc.build_parallelism())
    except Exception:
        return int(_setting("DEPLOY_BUILD_PARALLELISM", os.getenv("DEPLOY_BUILD_PARALLELISM", "1")))


# Lazy defaults — re-read from DB on each build via helpers below
DEFAULT_BUILD_CPU: float = 1.0
DEFAULT_BUILD_RAM_MB: int = 1024
DEFAULT_BUILD_PARALLELISM: int = 1


def _build_container_limits(
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return only resource keys supported by Docker's Build API.

    Runtime container controls such as NanoCpus/PidsLimit/ShmSize are NOT
    valid ``container_limits`` keys for ``APIClient.build()``. Passing them
    to docker-py 7.x can raise the misleading error "invalid tag ..." before
    the request is sent to Docker. Build resources remain server-owned; CPU is
    represented as a relative cpu-shares weight because the build API does not
    accept NanoCpus/CpuQuota in ``container_limits``.
    """
    from deployments.common.resource_policy import build_limits
    policy = dict(policy or build_limits())
    cpu = max(0.1, float(policy["cpu"]))
    ram = max(64, int(policy["memory_mb"]))
    # Docker's documented build-time container_limits supports cpushares.
    # Keep the mapping deterministic and bounded to Docker's accepted range.
    cpu_shares = max(2, min(262144, int(round(cpu * 1024))))
    mem_bytes = ram * 1024 * 1024
    return {
        "memory": mem_bytes,
        "memswap": mem_bytes,
        "cpushares": cpu_shares,
    }


# ---------------------------------------------------------------------------
# Safe tar extraction
# ---------------------------------------------------------------------------

def safe_extract(
    tar: tarfile.TarFile,
    path: str,
    max_bytes: int = 500 * 1024 * 1024,
) -> None:
    abs_base = os.path.abspath(path)
    total_written = 0

    for member in tar.getmembers():
        if member.islnk() or member.issym():
            raise Exception(
                f"Tar contains links which aren't allowed: {member.name}"
            )

        member_path = os.path.join(path, member.name)
        abs_target = os.path.abspath(member_path)

        if not abs_target.startswith(abs_base + os.sep) and abs_target != abs_base:
            raise Exception(f"Unsafe tar path detected: {member.name}")

        if member.isdir():
            os.makedirs(abs_target, exist_ok=True)
            try:
                os.chmod(abs_target, member.mode)
            except Exception:
                pass
            continue

        if not member.isreg():
            raise Exception(
                f"Unsupported tar entry (not a regular file): {member.name}"
            )

        parent = os.path.dirname(abs_target)
        if os.path.exists(parent) and not os.path.isdir(parent):
            os.remove(parent)
        os.makedirs(parent, exist_ok=True)

        f = tar.extractfile(member)
        if f is None:
            open(abs_target, "wb").close()
            continue

        with open(abs_target, "wb") as out_f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                total_written += len(chunk)
                if total_written > max_bytes:
                    raise Exception("Extracted data exceeds allowed limit")

        try:
            os.chmod(abs_target, member.mode)
        except Exception:
            pass


def flatten_single_toplevel(build_root: str) -> str | None:
    """
    If the extracted archive contains exactly one top-level directory
    (and no other files/dirs at the root), move its contents up one level.

    This is the #1 cause of PHP/Apache DocumentRoot failures: GitHub zips
    and many CI artifacts unpack as ``MyApp/public/index.php`` instead of
    ``public/index.php``. After flattening, COPY . /var/www/html puts
    files where the Dockerfile and Apache conf expect them.

    Returns the name of the stripped directory (for logging), or None
    when no strip was performed.
    """
    try:
        entries = [
            e for e in os.listdir(build_root)
            if e not in (".", "..", "Dockerfile", ".dockerignore")
        ]
    except OSError:
        return None

    if len(entries) != 1:
        return None

    only = entries[0]
    only_path = os.path.join(build_root, only)
    if not os.path.isdir(only_path):
        return None

    # Safety: refuse if the single dir itself looks like a system dir
    if only in ("bin", "etc", "usr", "var", "lib", "opt", "tmp", "dev", "proc"):
        return None

    import shutil

    for item in os.listdir(only_path):
        src = os.path.join(only_path, item)
        dst = os.path.join(build_root, item)
        if os.path.exists(dst):
            # Conflict — abort flatten to avoid data loss
            return None
        shutil.move(src, dst)

    try:
        os.rmdir(only_path)
    except OSError:
        pass

    return only


# ---------------------------------------------------------------------------
# Docker image naming
# ---------------------------------------------------------------------------
# The deployment models are authoritative: ``Service.get_docker_service_name()``
# provides the repository/container name and ``Deploy.version`` provides the tag.
# We validate those values but never invent a staging name or rewrite the version.

_VALID_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_VALID_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def _validate_image_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValueError("Image name must not be empty")
    value = name.strip()
    if value != name:
        raise ValueError(f"Image name contains surrounding whitespace: {name!r}")
    if len(value) > 255 or not _VALID_NAME_RE.fullmatch(value):
        raise ValueError(f"Invalid Docker image repository name: {value!r}")
    return value


def _validate_image_tag(tag: Any) -> str:
    value = "latest" if tag is None else str(tag).strip()
    if not value:
        value = "latest"
    if len(value) > 128 or not _VALID_TAG_RE.fullmatch(value):
        raise ValueError(f"Invalid Docker image tag: {value!r}")
    return value


def _make_image_ref(name: str, tag: Any) -> str:
    return f"{_validate_image_name(name)}:{_validate_image_tag(tag)}"


# ---------------------------------------------------------------------------
# Image manager
# ---------------------------------------------------------------------------

class Image(Client):
    def __init__(
        self,
        name: str,
        tag: str = "latest",
        dockerfile_text: str = None,
        tarfile: io.BytesIO = None,
        *,
        max_cpu: float | None = None,
        max_ram: int | None = None,
        build_options: dict[str, Any] | None = None,
        build_resource_policy: dict[str, Any] | None = None,
        deployment_id: Any | None = None,
    ):
        super().__init__()
        self.name = _validate_image_name(name)
        self.tag = _validate_image_tag(tag)
        self.dockerfile_text = dockerfile_text
        self.tarfile = tarfile
        self.image_ref = _make_image_ref(self.name, self.tag)
        # Keep name/tag in sync with image_ref
        if ":" in self.image_ref:
            self.name, self.tag = self.image_ref.rsplit(":", 1)
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.build_options = dict(build_options or {})
        self.build_resource_policy = dict(build_resource_policy or {})
        self.deployment_id = deployment_id
        if not self.name:
            raise ValueError("Image name must not be empty")

    def _iter_build_stream(self, stream):
        for chunk in stream:
            if isinstance(chunk, (bytes, bytearray)):
                try:
                    text = chunk.decode("utf-8", "replace")
                    for line in text.splitlines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            yield {"stream": line}
                except Exception:
                    yield {"stream": repr(chunk)}
            elif isinstance(chunk, dict):
                yield chunk
            else:
                try:
                    yield {"stream": str(chunk)}
                except Exception:
                    yield {"stream": repr(chunk)}

    def _handle_build_stream(
        self,
        response,
        on_build_output: Optional[Callable] = None,
    ) -> None:
        for chunk in self._iter_build_stream(response):
            if on_build_output:
                try:
                    on_build_output(chunk)
                except Exception:
                    logger.exception("on_build_output callback failed")

            if "stream" in chunk:
                msg = (chunk.get("stream") or "").strip()
                if msg:
                    logger.info(msg)
            elif "status" in chunk:
                status = chunk.get("status")
                progress = chunk.get("progress")
                if progress:
                    logger.info("%s %s", status, progress)
                else:
                    logger.info("%s", status)
            elif "error" in chunk:
                logger.error(chunk.get("error"))
                raise BuildError(chunk.get("error"), build_log=[chunk])
            else:
                logger.debug("Build chunk: %s", chunk)


    def _tag_image(self, image_id: str) -> None:
        """Tag image by ID via low-level API (avoids broken match_tag)."""
        repo = self.name
        tag = self.tag or "latest"
        try:
            ok = self.client.api.tag(
                image_id, repository=repo, tag=tag, force=True
            )
            logger.info(
                "Tagged image %s as %s:%s (ok=%s)",
                (image_id or "")[:12],
                repo,
                tag,
                ok,
            )
        except Exception:
            logger.exception(
                "api.tag failed for %s → %s:%s; trying images.get().tag()",
                (image_id or "")[:12],
                repo,
                tag,
            )
            img = self.client.images.get(image_id)
            img.tag(repository=repo, tag=tag)

    def _handle_build_stream_collect_id(
        self,
        response,
        on_build_output: Optional[Callable] = None,
    ) -> Optional[str]:
        """Consume build stream, log output, return final image ID."""
        image_id: Optional[str] = None

        for chunk in self._iter_build_stream(response):
            if on_build_output:
                try:
                    on_build_output(chunk)
                except Exception:
                    logger.exception("on_build_output callback failed")

            if not isinstance(chunk, dict):
                continue

            aux = chunk.get("aux") or {}
            if isinstance(aux, dict):
                cid = aux.get("ID") or aux.get("Id")
                if cid:
                    image_id = cid

            if "stream" in chunk:
                msg = (chunk.get("stream") or "").strip()
                if msg:
                    logger.info(msg)
                    m = re.search(
                        r"Successfully built ([0-9a-f]{12,})",
                        msg,
                        re.IGNORECASE,
                    )
                    if m:
                        image_id = m.group(1)
                    m2 = re.search(
                        r"writing image (sha256:[0-9a-f]+)",
                        msg,
                        re.IGNORECASE,
                    )
                    if m2:
                        image_id = m2.group(1)
            elif "status" in chunk:
                status = chunk.get("status")
                progress = chunk.get("progress")
                if progress:
                    logger.info("%s %s", status, progress)
                else:
                    logger.info("%s", status)
            elif "error" in chunk or "errorDetail" in chunk:
                err = chunk.get("error") or (
                    (chunk.get("errorDetail") or {}).get("message")
                )
                logger.error(err)
                raise BuildError(str(err), build_log=[chunk])
            else:
                logger.debug("Build chunk: %s", chunk)

        return image_id


    def create(self, on_build_output: Optional[Callable] = None):
        """Build the exact model-derived image and apply its tag after build.

        The low-level docker-py ``api.build`` path is used with the exact
        ``Deploy.version`` as the API's tag-only argument. docker-py validates
        this value before sending the request, so ``None`` is never passed.
        The exact ``Service`` repository name is then applied to the returned
        image ID with ``api.tag``. No synthetic/staging image name or rewritten
        version is ever introduced.
        """
        if not self.dockerfile_text or not self.tarfile:
            raise ValueError("dockerfile_text and tarfile are required")

        build_policy = dict(self.build_resource_policy or {})
        if not build_policy:
            from deployments.common.resource_policy import build_limits
            build_policy = dict(build_limits())
        effective_cpu = max(0.1, float(build_policy["cpu"]))
        effective_ram = max(64, int(build_policy["memory_mb"]))
        limits = _build_container_limits(policy=build_policy)
        build_shm_size = max(1, int(build_policy.get("shm_size_mb", 64))) * 1024 * 1024
        target_ref = self.image_ref

        logger.info(
            "Building image repository=%r tag=%r cpu=%.2f ram=%d MB",
            self.name, self.tag, effective_cpu, effective_ram,
        )

        buildargs = {"BUILDKIT_INLINE_CACHE": "1"}

        try:
            with BuildSlot(deployment_id=self.deployment_id or target_ref, logger=logger):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tar_stream = (
                        io.BytesIO(self.tarfile)
                        if isinstance(self.tarfile, (bytes, bytearray))
                        else self.tarfile
                    )
                    tar_stream.seek(0)
                    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
                        safe_extract(tar, tmpdir, max_bytes=500 * 1024 * 1024)

                    stripped = flatten_single_toplevel(tmpdir)
                    if stripped:
                        logger.info(
                            "Stripped single top-level archive directory '%s' from build context.",
                            stripped,
                        )

                    build_path = tmpdir
                    app_dir = os.path.join(tmpdir, "app")
                    if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, "Dockerfile")):
                        build_path = app_dir
                    else:
                        with open(os.path.join(tmpdir, "Dockerfile"), "w", encoding="utf-8") as f:
                            f.write(self.dockerfile_text)

                    df_path = os.path.join(build_path, "Dockerfile")
                    if not os.path.isfile(df_path):
                        with open(df_path, "w", encoding="utf-8") as f:
                            f.write(self.dockerfile_text)

                    # docker-py 7.x validates BuildApiMixin.build(tag=...) as a
                    # *tag only*, not as a full repository:tag reference, and
                    # rejects tag=None before the request reaches Docker. The
                    # repository is derived by Docker from the build context's
                    # resulting image reference; ``self.name`` is applied
                    # immediately after the build by _tag_image().
                    # IMPORTANT: never synthesize or rewrite the model-provided
                    # name/version. The Deploy model owns the tag.
                    build_options = dict(self.build_options or {})
                    extra_build = {}
                    if bool(build_options.get("no_cache")):
                        extra_build["nocache"] = True
                    if bool(build_options.get("pull")):
                        extra_build["pull"] = True

                    attempt_kwargs = [
                        dict(path=build_path, tag=self.tag, rm=True, forcerm=True, decode=True,
                             container_limits=limits, shmsize=build_shm_size, buildargs=buildargs,
                             network_mode="default", **extra_build),
                        dict(path=build_path, tag=self.tag, rm=True, forcerm=True, decode=True,
                             shmsize=build_shm_size, buildargs=buildargs, **extra_build),
                        dict(path=build_path, tag=self.tag, rm=True, forcerm=True, decode=True, **extra_build),
                    ]

                    response = None
                    last_err = None
                    for i, kwargs in enumerate(attempt_kwargs):
                        try:
                            logger.info("api.build attempt %d kwargs=%s", i + 1, sorted(k for k in kwargs if k != "path"))
                            response = self.client.api.build(**kwargs)
                            last_err = None
                            break
                        except TypeError as exc:
                            last_err = exc
                            logger.warning("api.build attempt %d TypeError: %s", i + 1, exc)
                        except docker.errors.DockerException as exc:
                            last_err = exc
                            logger.warning("api.build attempt %d DockerException: %s: %s", i + 1, type(exc).__name__, exc)
                            break
                        except Exception as exc:
                            last_err = exc
                            logger.warning("api.build attempt %d %s: %s", i + 1, type(exc).__name__, exc)
                            break

                    if response is None:
                        raise ImageBuildError(
                            f"Docker api.build failed: {type(last_err).__name__ if last_err else 'unknown'}: {last_err}",
                            details={"image": target_ref, "error": str(last_err), "error_type": type(last_err).__name__ if last_err else None},
                        ) from last_err

                    image_id = self._handle_build_stream_collect_id(
                        response, on_build_output=on_build_output
                    )
                    if not image_id:
                        raise ImageBuildError(
                            "Docker build finished but no image ID was returned by the build stream.",
                            details={"image": target_ref},
                        )

                    # Preserve the exact repository and exact Deploy.version tag.
                    self._tag_image(image_id)
                    logger.info("Docker image built and tagged: %s", target_ref)
                    try:
                        return self.client.images.get(target_ref)
                    except ImageNotFound:
                        return self.client.images.get(image_id)

        except BuildError as exc:
            raise ImageBuildError(
                "Docker image build failed.",
                details={"image": target_ref, "error": str(exc)},
            ) from exc
        except ImageBuildError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error while building Docker image: %s: %s",
                type(exc).__name__, exc,
            )
            logger.error(traceback.format_exc())
            raise ImageBuildError(
                f"Unexpected error while building Docker image: {type(exc).__name__}: {exc}",
                details={"image": target_ref, "error": str(exc), "error_type": type(exc).__name__},
            ) from exc


    def inspect(self):
        image = self.client.images.get(self.image_ref)
        return image.attrs

    def history(self):
        return self.client.api.history(self.image_ref)

    def size(self):
        attrs = self.inspect()
        return attrs.get("Size", 0)

    def labels(self):
        attrs = self.inspect()
        return attrs.get("Config", {}).get("Labels", {}) or {}

    def save_to_path(self, path: str):
        image = self.client.images.get(self.image_ref)
        stream = image.save(named=True)
        with open(path, "wb") as f:
            for chunk in stream:
                f.write(chunk)
        return path

    def save_to_fileobj(self, fileobj):
        image = self.client.images.get(self.image_ref)
        stream = image.save(named=True)
        for chunk in stream:
            fileobj.write(chunk)
        fileobj.flush()
        return fileobj

    @classmethod
    def remove_by_name(cls, name):
        client = Client()()
        try:
            image = client.images.get(name)
        except ImageNotFound:
            logger.info("Image '%s' not found (nothing to remove)", name)
            return False
        except Exception as e:
            logger.error("Error while fetching image '%s': %s", name, e)
            raise

        try:
            client.images.remove(image.id)
            logger.info(
                "Image '%s' removed successfully (id=%s)", name, image.id
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to remove image '%s' (id=%s): %s",
                name,
                getattr(image, "id", None),
                e,
            )
            raise

    @classmethod
    def check_exists(cls, name):
        client = Client()()
        try:
            client.images.get(name)
            return True
        except ImageNotFound:
            return False
        except Exception as e:
            logger.error(
                "Error while checking existence of image '%s': %s", name, e
            )
            raise

    def remove(self, force: bool = False) -> bool:
        try:
            try:
                image = self.client.images.get(self.image_ref)
            except ImageNotFound:
                logger.debug(
                    "Image '%s' not found (nothing to remove)", self.image_ref
                )
                return True

            image_id_short = (
                image.id[:12] if hasattr(image, "id") else "unknown"
            )

            try:
                self.client.images.remove(self.image_ref, force=force)
                logger.info(
                    "Image '%s' (ID: %s) removed successfully",
                    self.image_ref,
                    image_id_short,
                )
                return True

            except docker.errors.APIError as e:
                if "referenced in multiple repositories" in str(e):
                    if force:
                        self.client.images.remove(self.image_ref, force=True)
                        return True
                    self.client.images.remove(self.image_ref)
                    return True
                logger.error(
                    "Docker API error removing '%s': %s", self.image_ref, e
                )
                raise

        except Exception as e:
            logger.error(
                "Unexpected error removing image '%s': %s", self.image_ref, e
            )
            return False

    def remove_all(
        self,
        force: bool = False,
        keep_latest: bool = False,
        keep_tags=None,
    ) -> dict:
        stats = {
            "total_found": 0,
            "removed": 0,
            "skipped": 0,
            "failed": 0,
            "kept": [],
        }
        try:
            try:
                images = self.client.images.list(name=self.name)
                if not images:
                    all_images = self.client.images.list()
                    images = [
                        img
                        for img in all_images
                        if any(self.name in tag for tag in img.tags)
                    ]
                stats["total_found"] = len(images)
                if not images:
                    return stats
            except Exception as e:
                logger.error("Error listing images: %s", e)
                return stats

            images_sorted = sorted(
                images,
                key=lambda x: x.attrs.get("Created", ""),
                reverse=True,
            )
            keep_tags = list(keep_tags or [])
            if keep_latest and images_sorted:
                keep_tags.extend(images_sorted[0].tags)

            for image in images_sorted:
                should_keep = any(tag in keep_tags for tag in image.tags)
                if should_keep:
                    stats["skipped"] += 1
                    stats["kept"].extend(image.tags)
                    continue
                if self._remove_image_with_tags(image, force):
                    stats["removed"] += 1
                else:
                    stats["failed"] += 1
            return stats
        except Exception as e:
            logger.error("Error in remove_all for '%s': %s", self.name, e)
            return stats

    def _remove_image_with_tags(self, image, force: bool = False) -> bool:
        image_id = image.id[:12] if hasattr(image, "id") else "unknown"
        try:
            for tag in image.tags:
                try:
                    self.client.images.remove(tag, force=force)
                except docker.errors.APIError as e:
                    if "referenced in multiple repositories" in str(e):
                        self.client.images.remove(tag, force=True)
                    else:
                        logger.warning("Could not remove tag '%s': %s", tag, e)
            try:
                self.client.images.remove(image.id, force=True)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error("Failed to remove image with ID %s: %s", image_id, e)
            return False

    def list_all(self):
        try:
            images = self.client.images.list(name=self.name)
            result = []
            for img in images:
                result.append(
                    {
                        "id": img.id[:12],
                        "tags": img.tags,
                        "created": img.attrs.get("Created", ""),
                        "size": img.attrs.get("Size", 0),
                        "virtual_size": img.attrs.get("VirtualSize", 0),
                    }
                )
            result.sort(key=lambda x: x["created"], reverse=True)
            return result
        except Exception as e:
            logger.error("Error listing images for '%s': %s", self.name, e)
            return []

    def exists(self) -> bool:
        try:
            self.client.images.get(self.image_ref)
            return True
        except ImageNotFound:
            return False

    def get_image_info(self):
        try:
            image = self.client.images.get(self.image_ref)
            return {
                "id": image.id,
                "tags": image.tags,
                "created": image.attrs.get("Created", ""),
                "size": image.attrs.get("Size", 0),
                "virtual_size": image.attrs.get("VirtualSize", 0),
                "labels": image.attrs.get("Labels", {}),
                "architecture": image.attrs.get("Architecture", ""),
            }
        except ImageNotFound:
            return None

    @classmethod
    def prune_dangling_images(cls):
        try:
            client = Client()()
            client.images.prune(filters={"dangling": True})
        except Exception as exc:
            raise CleanupError(
                "Failed to prune dangling Docker images."
            ) from exc
