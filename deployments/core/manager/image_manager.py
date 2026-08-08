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
    max_cpu: float | None = None,
    max_ram_mb: int | None = None,
) -> dict[str, Any]:
    cpu = float(max_cpu if max_cpu is not None else _build_default_cpu())
    ram = int(max_ram_mb if max_ram_mb is not None else _build_default_ram())
    cpu = max(0.1, min(cpu, 32.0))
    ram = max(128, min(ram, 65536))
    nano_cpus = int(cpu * 1_000_000_000)
    mem_bytes = ram * 1024 * 1024
    return {
        "Memory": mem_bytes,
        "MemorySwap": mem_bytes,
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
# Reference sanitization — fixes "invalid tag ... invalid reference format"
# ---------------------------------------------------------------------------
#
# Some docker-py / daemon versions reject tags that are pure version numbers
# like "1.22" or "1.00". We always produce a tag that starts with a letter
# and uses only [A-Za-z0-9_.-].

_VALID_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
# Full reference as accepted by common docker-py match_tag implementations
_SAFE_REF_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-zA-Z][a-zA-Z0-9._-]{0,127})?$"
)


def _sanitize_image_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValueError("Image name must not be empty")
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9._-]", "-", cleaned)
    cleaned = re.sub(r"[._-]{2,}", "-", cleaned).strip("._-")
    if not cleaned or not _VALID_NAME_RE.match(cleaned):
        cleaned = re.sub(r"[^a-z0-9]", "", cleaned) or "image"
    return cleaned[:255]


def _sanitize_image_tag(tag: Any) -> str:
    """
    Return a Docker-legal tag that starts with a letter.

    Examples
    --------
    1.22  → v1-22
    1.00  → v1-00
    v1.2  → v1.2
    latest → latest
    """
    if tag is None:
        return "latest"
    t = str(tag).strip()
    if not t:
        return "latest"

    # Strip leading v/V for normalization, then re-apply
    raw = t
    if t.lower().startswith("v") and len(t) > 1 and t[1].isdigit():
        raw = t[1:]

    # Pure numeric / semver style (digits and dots/hyphens only)
    if re.match(r"^[\d]+([.\-][\d]+)*$", raw):
        # Prefer hyphens over dots — maximally compatible with strict match_tag
        safe = "v" + raw.replace(".", "-")
        return safe[:128]

    # General sanitization
    t = re.sub(r"[^a-zA-Z0-9_.-]", "-", t)
    t = t.strip(".-")
    if not t:
        return "latest"
    # Must start with letter or underscore (not digit, not dot, not hyphen)
    if not re.match(r"^[a-zA-Z_]", t):
        t = "v" + t
    return t[:128]


def _make_safe_ref(name: str, tag: str) -> str:
    n = _sanitize_image_name(name)
    t = _sanitize_image_tag(tag)
    ref = f"{n}:{t}"
    if not _SAFE_REF_RE.match(ref):
        # Last resort
        t2 = re.sub(r"[^a-zA-Z0-9-]", "-", t)
        if not re.match(r"^[a-zA-Z_]", t2):
            t2 = "v" + t2
        ref = f"{n}:{t2[:128]}"
    return ref


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
        super().__init__()
        self.name = _sanitize_image_name(name)
        self.tag = _sanitize_image_tag(tag)
        self.dockerfile_text = dockerfile_text
        self.tarfile = tarfile
        self.image_ref = _make_safe_ref(self.name, self.tag)
        # Keep name/tag in sync with image_ref
        if ":" in self.image_ref:
            self.name, self.tag = self.image_ref.rsplit(":", 1)
        self.max_cpu = max_cpu
        self.max_ram = max_ram
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
        """
        Build Docker image without passing tag= (avoids broken match_tag).

        Also degrades gracefully if container_limits / network_mode are
        unsupported by the installed docker-py or engine.
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
        target_ref = self.image_ref

        logger.info(
            "Building image %s (untagged → tag after) cpu=%.2f ram=%d MB",
            target_ref,
            effective_cpu,
            effective_ram,
        )
        try:
            import docker as _docker_mod

            logger.info(
                "docker-py=%s name=%r tag=%r",
                getattr(_docker_mod, "__version__", "?"),
                self.name,
                self.tag,
            )
        except Exception:
            pass

        buildargs = {"BUILDKIT_INLINE_CACHE": "1"}

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

                # Ensure Dockerfile exists at build root
                df_path = os.path.join(build_path, "Dockerfile")
                if not os.path.isfile(df_path):
                    with open(df_path, "w", encoding="utf-8") as f:
                        f.write(self.dockerfile_text)

                logger.info(
                    "Build context ready path=%s files=%s",
                    build_path,
                    len(os.listdir(build_path)),
                )

                # Try progressively simpler kwargs so unsupported options
                # never abort the whole deploy.
                attempt_kwargs = [
                    dict(
                        path=build_path,
                        rm=True,
                        forcerm=True,
                        decode=True,
                        container_limits=limits,
                        buildargs=buildargs,
                        network_mode="default",
                    ),
                    dict(
                        path=build_path,
                        rm=True,
                        forcerm=True,
                        decode=True,
                        buildargs=buildargs,
                    ),
                    dict(
                        path=build_path,
                        rm=True,
                        forcerm=True,
                        decode=True,
                    ),
                ]

                response = None
                last_err: Exception | None = None
                for i, kwargs in enumerate(attempt_kwargs):
                    try:
                        logger.info(
                            "api.build attempt %d kwargs=%s",
                            i + 1,
                            sorted(k for k in kwargs if k != "path"),
                        )
                        response = self.client.api.build(**kwargs)
                        last_err = None
                        break
                    except TypeError as exc:
                        # Unknown kwarg for this docker-py version
                        logger.warning(
                            "api.build attempt %d TypeError: %s", i + 1, exc
                        )
                        last_err = exc
                    except docker.errors.DockerException as exc:
                        msg = str(exc).lower()
                        # Still the broken match_tag? (should not happen without tag=)
                        logger.warning(
                            "api.build attempt %d DockerException: %s: %s",
                            i + 1,
                            type(exc).__name__,
                            exc,
                        )
                        last_err = exc
                        # If somehow tag validation still triggers, continue
                        if "invalid tag" in msg or "invalid reference" in msg:
                            continue
                        # Other docker errors (daemon down, etc.) — stop
                        break
                    except Exception as exc:
                        logger.warning(
                            "api.build attempt %d %s: %s",
                            i + 1,
                            type(exc).__name__,
                            exc,
                        )
                        last_err = exc
                        break

                if response is None:
                    raise ImageBuildError(
                        f"Docker api.build failed: "
                        f"{type(last_err).__name__ if last_err else 'unknown'}: "
                        f"{last_err}",
                        details={
                            "image": target_ref,
                            "error": str(last_err),
                            "error_type": type(last_err).__name__
                            if last_err
                            else None,
                        },
                    ) from last_err

                image_id = self._handle_build_stream_collect_id(
                    response, on_build_output=on_build_output
                )

                if not image_id:
                    # SECURITY/RELIABILITY: the legacy code fell back to
                    # ``dangling[0].id`` here, which could pick up an
                    # UNRELATED dangling image and silently tag it as the
                    # deployment image — deploying the wrong code.  We
                    # now fail loudly instead of guessing.
                    raise ImageBuildError(
                        "Docker build finished but no image ID was returned "
                        "by the build stream. Refusing to guess a dangling image.",
                        details={
                            "image": target_ref,
                            "hint": (
                                "Enable BuildKit (DOCKER_BUILDKIT=1) or upgrade "
                                "docker-py to a version that emits 'writing image "
                                "sha256:...' in the build stream."
                            ),
                        },
                    )

                self._tag_image(image_id)

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
                type(exc).__name__,
                exc,
            )
            logger.error(traceback.format_exc())
            raise ImageBuildError(
                f"Unexpected error while building Docker image: "
                f"{type(exc).__name__}: {exc}",
                details={
                    "image": target_ref,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
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
