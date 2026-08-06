from __future__ import annotations

import io
import json
import logging
import os
import re
import tarfile
import tempfile
import traceback
from typing import Any, Callable, Optional

import docker
import docker.errors
from docker.errors import BuildError, ImageNotFound

from deployments.core.exceptions import CleanupError, ImageBuildError
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


DEFAULT_BUILD_CPU: float = float(
    _setting("DEPLOY_BUILD_MAX_CPU", os.getenv("DEPLOY_BUILD_MAX_CPU", "1.0"))
)
DEFAULT_BUILD_RAM_MB: int = int(
    _setting("DEPLOY_BUILD_MAX_RAM_MB", os.getenv("DEPLOY_BUILD_MAX_RAM_MB", "1024"))
)
DEFAULT_BUILD_PARALLELISM: int = int(
    _setting("DEPLOY_BUILD_PARALLELISM", os.getenv("DEPLOY_BUILD_PARALLELISM", "1"))
)


def _build_container_limits(
    *,
    max_cpu: float | None = None,
    max_ram_mb: int | None = None,
) -> dict[str, Any]:
    """
    Return the ``container_limits`` dict for the Docker Engine build API.

    Keys (Engine API):
      Memory / MemorySwap  – bytes
      NanoCpus             – 10^-9 CPU units
      CpuPeriod / CpuQuota – cgroup v1 fallback
    """
    cpu = float(max_cpu if max_cpu is not None else DEFAULT_BUILD_CPU)
    ram = int(max_ram_mb if max_ram_mb is not None else DEFAULT_BUILD_RAM_MB)

    # Hard safety clamps
    cpu = max(0.1, min(cpu, 32.0))
    ram = max(128, min(ram, 65536))

    nano_cpus = int(cpu * 1_000_000_000)
    mem_bytes = ram * 1024 * 1024

    return {
        "Memory": mem_bytes,
        "MemorySwap": mem_bytes,  # no extra swap beyond the hard limit
        "NanoCpus": nano_cpus,
        "CpuPeriod": 100_000,
        "CpuQuota": int(cpu * 100_000),
    }


# ---------------------------------------------------------------------------
# Safe tar extraction
# ---------------------------------------------------------------------------

def safe_extract(
    tar: tarfile.TarFile,
    path: str,
    max_bytes: int = 500 * 1024 * 1024,
) -> None:
    """
    Extract tar safely into ``path``.

    - Prevents path traversal
    - Rejects symlinks and hard links
    - Limits total extracted bytes to ``max_bytes``
    """
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


# ---------------------------------------------------------------------------
# Reference sanitization (prevents "invalid reference format")
# ---------------------------------------------------------------------------

_VALID_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_VALID_TAG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$")


def _sanitize_image_name(name: str) -> str:
    """Force a Docker-legal lowercase repository name."""
    if not name or not isinstance(name, str):
        raise ValueError("Image name must not be empty")
    cleaned = name.strip().lower()
    # Collapse consecutive separators that Docker rejects
    cleaned = re.sub(r"[._-]{2,}", "-", cleaned)
    cleaned = cleaned.strip("._-")
    if not cleaned or not _VALID_NAME_RE.match(cleaned):
        # Last-resort safe name
        cleaned = re.sub(r"[^a-z0-9._-]", "-", cleaned)
        cleaned = re.sub(r"[._-]{2,}", "-", cleaned).strip("._-") or "image"
    return cleaned


def _sanitize_image_tag(tag: Any) -> str:
    """Return a Docker-legal tag (never empty, never starts with . or -)."""
    if tag is None:
        return "latest"
    t = str(tag).strip()
    if not t:
        return "latest"
    # Common case: version numbers like 1.00 / 1.0 → keep them
    if _VALID_TAG_RE.match(t):
        return t
    # Make it legal: drop illegal chars, ensure first char is alnum/underscore
    t = re.sub(r"[^a-zA-Z0-9_.-]", "-", t)
    t = t.strip(".-")
    if not t or not re.match(r"^[a-zA-Z0-9_]", t):
        t = f"v{t}" if t else "latest"
    return t[:128]


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
    ):
        """
        Parameters
        ----------
        name, tag, dockerfile_text, tarfile
            Standard build inputs.
        max_cpu : float, optional
            CPU cores the *build* container may use (overrides
            ``DEPLOY_BUILD_MAX_CPU``).  Typically taken from the service plan.
        max_ram : int, optional
            RAM in megabytes for the build container (overrides
            ``DEPLOY_BUILD_MAX_RAM_MB``).
        """
        super().__init__()
        self.name = _sanitize_image_name(name)
        self.tag = _sanitize_image_tag(tag)
        self.dockerfile_text = dockerfile_text
        self.tarfile = tarfile
        self.image_ref = f"{self.name}:{self.tag}"
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        if not self.name:
            raise ValueError("Image name must not be empty")

    # ------------------------------------------------------------------
    # Build stream helpers
    # ------------------------------------------------------------------

    def _iter_build_stream(self, stream):
        """Normalize build stream chunks to dicts (bytes or dict)."""
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
        """Log each chunk and optionally forward to the caller callback."""
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

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def create(self, on_build_output: Optional[Callable] = None):
        """
        Build the image with CPU / memory limits so concurrent deploys
        cannot exhaust the host.

        If ``on_build_output`` is provided it is called for every build
        chunk (dict) as it arrives — useful for streaming to the UI.
        Returns the built image object.
        """
        if not self.dockerfile_text or not self.tarfile:
            raise ValueError("dockerfile_text and tarfile are required")

        limits = _build_container_limits(
            max_cpu=self.max_cpu,
            max_ram_mb=self.max_ram,
        )
        effective_cpu = (
            self.max_cpu if self.max_cpu is not None else DEFAULT_BUILD_CPU
        )
        effective_ram = (
            self.max_ram if self.max_ram is not None else DEFAULT_BUILD_RAM_MB
        )
        logger.info(
            "Building image %s with limits cpu=%.2f cores ram=%d MB",
            self.image_ref,
            effective_cpu,
            effective_ram,
        )

        buildargs = {
            "BUILDKIT_INLINE_CACHE": "1",
        }

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tar_stream = (
                    io.BytesIO(self.tarfile)
                    if isinstance(self.tarfile, (bytes, bytearray))
                    else self.tarfile
                )

                tar_stream.seek(0)
                with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
                    safe_extract(tar, tmpdir, max_bytes=500 * 1024 * 1024)

                build_path = tmpdir
                app_dir = os.path.join(tmpdir, "app")
                if os.path.isdir(app_dir) and os.path.exists(
                    os.path.join(app_dir, "Dockerfile")
                ):
                    build_path = app_dir
                else:
                    with open(
                        os.path.join(tmpdir, "Dockerfile"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(self.dockerfile_text)

                # Guaranteed legal reference – prevents the exact error you hit
                safe_tag = f"{self.name}:{self.tag}"
                logger.debug("Docker build tag (sanitized): %s", safe_tag)

                response = self.client.api.build(
                    path=build_path,
                    tag=safe_tag,
                    rm=True,
                    forcerm=True,
                    decode=True,
                    container_limits=limits,
                    buildargs=buildargs,
                    network_mode="default",
                )

                self._handle_build_stream(
                    response, on_build_output=on_build_output
                )
                return self.client.images.get(safe_tag)

        except BuildError as exc:
            raise ImageBuildError(
                "Docker image build failed.",
                details={
                    "image": self.image_ref,
                    "error": str(exc),
                },
            ) from exc
        except ImageBuildError:
            raise
        except Exception as exc:
            logger.error("Unexpected error while building Docker image")
            logger.error(traceback.format_exc())
            raise ImageBuildError(
                "Unexpected error while building Docker image.",
                details={
                    "image": self.image_ref,
                    "error": str(exc),
                },
            ) from exc

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def inspect(self):
        """Return docker inspect dict for this image (raises if missing)."""
        image = self.client.images.get(self.image_ref)
        return image.attrs

    def history(self):
        """Return image history (list of layers / commands)."""
        return self.client.api.history(self.image_ref)

    def size(self):
        """Return image size in bytes."""
        attrs = self.inspect()
        return attrs.get("Size", 0)

    def labels(self):
        """Return image labels dict (or {})."""
        attrs = self.inspect()
        return attrs.get("Config", {}).get("Labels", {}) or {}

    def save_to_path(self, path: str):
        """
        Save image as a tar archive to the given filesystem path.
        Writes incrementally (does not load everything into memory).
        """
        image = self.client.images.get(self.image_ref)
        stream = image.save(named=True)
        with open(path, "wb") as f:
            for chunk in stream:
                f.write(chunk)
        return path

    def save_to_fileobj(self, fileobj):
        """
        Write image tar to a file-like object (must be opened for binary write).
        """
        image = self.client.images.get(self.image_ref)
        stream = image.save(named=True)
        for chunk in stream:
            fileobj.write(chunk)
        fileobj.flush()
        return fileobj

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def remove_by_name(cls, name):
        """
        Remove image by name (may include tag, e.g. ``repo:tag``, or be an id).
        Returns True if removed, False if not found.
        Raises on unexpected errors.
        """
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
        """
        Check whether an image exists (name may include tag).
        Returns True if exists, False otherwise.
        """
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

    # ------------------------------------------------------------------
    # Instance removal
    # ------------------------------------------------------------------

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
                    logger.warning(
                        "Image '%s' has multiple tags (%s)",
                        self.image_ref,
                        image.tags,
                    )
                    if force:
                        self.client.images.remove(self.image_ref, force=True)
                        logger.info(
                            "Image '%s' force removed", self.image_ref
                        )
                        return True
                    logger.info(
                        "Only removing tag '%s' from image", self.image_ref
                    )
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
                    logger.info("No images found with name '%s'", self.name)
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
                should_keep = False
                for tag in image.tags:
                    if tag in keep_tags:
                        should_keep = True
                        stats["kept"].append(tag)
                        break

                if should_keep:
                    stats["skipped"] += 1
                    logger.debug("Skipping image with tags: %s", image.tags)
                    continue

                if self._remove_image_with_tags(image, force):
                    stats["removed"] += 1
                else:
                    stats["failed"] += 1

            logger.info(
                "Remove all completed for '%s': "
                "%s removed, %s skipped, %s failed, %s kept",
                self.name,
                stats["removed"],
                stats["skipped"],
                stats["failed"],
                len(stats["kept"]),
            )
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
                    logger.debug("Removed tag: %s", tag)
                except docker.errors.APIError as e:
                    if "referenced in multiple repositories" in str(e):
                        self.client.images.remove(tag, force=True)
                        logger.debug("Force removed tag: %s", tag)
                    else:
                        logger.warning(
                            "Could not remove tag '%s': %s", tag, e
                        )

            try:
                self.client.images.remove(image.id, force=True)
                logger.debug("Removed image ID: %s", image_id)
            except Exception as e:
                logger.debug(
                    "Image ID %s might already be removed: %s", image_id, e
                )

            return True

        except Exception as e:
            logger.error(
                "Failed to remove image with ID %s: %s", image_id, e
            )
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
            if self.tag:
                self.client.images.get(f"{self.name}:{self.tag}")
            else:
                images = self.client.images.list(name=self.name)
                return len(images) > 0
            return True
        except ImageNotFound:
            return False

    def get_image_info(self):
        try:
            if not self.tag:
                return None
            image = self.client.images.get(f"{self.name}:{self.tag}")
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