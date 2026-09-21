"""
deployments/core/converter.py
-----------------------------
ZIP → TAR conversion with hard security limits and central path checks.
"""

from __future__ import annotations

import io
import os
import tarfile
import zipfile

from deployments.common.exceptions import DeploymentValidationError, DeploymentSecurityError
from deployments.common.security import is_safe_archive_name, is_zip_symlink


MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000


def merge_tar_streams(*streams: io.BytesIO) -> io.BytesIO:
    combined = io.BytesIO()
    with tarfile.open(fileobj=combined, mode="w") as tar_out:
        for stream in streams:
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode="r") as tar_in:
                for member in tar_in.getmembers():
                    file_data = tar_in.extractfile(member)
                    if file_data is not None:
                        tar_out.addfile(member, file_data)
                    else:
                        tar_out.addfile(member)
    combined.seek(0)
    return combined


def convert_zip_to_tar(zip_path: str) -> io.BytesIO:
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP file not found at: {zip_path}")

    tar_stream = io.BytesIO()
    total_uncompressed = 0

    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        with zipfile.ZipFile(zip_path, "r") as zipf:
            members = zipf.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise DeploymentValidationError(
                    "ZIP archive contains too many files.",
                    stage="archive_validation",
                    details={
                        "max_members": MAX_ARCHIVE_MEMBERS,
                        "actual_members": len(members),
                    },
                )

            for zip_info in members:
                # Normalize early so both dirs and files share the same checks
                member_name = zip_info.filename.replace("\\", "/").lstrip("./")
                if not member_name or member_name in {".", ".."}:
                    continue

                if not is_safe_archive_name(member_name):
                    raise DeploymentSecurityError(
                        "ZIP archive contains an unsafe file path "
                        "(path traversal or absolute path).",
                        stage="archive_validation",
                        details={"filename": zip_info.filename},
                    )

                if is_zip_symlink(zip_info):
                    raise DeploymentSecurityError(
                        "ZIP archive contains symbolic links, which are not allowed.",
                        stage="archive_validation",
                        details={"filename": zip_info.filename},
                    )

                if zip_info.is_dir():
                    # Preserve directory entries (important for empty dirs
                    # such as Laravel storage/framework/cache).
                    dir_name = member_name.rstrip("/") + "/"
                    tar_info = tarfile.TarInfo(name=dir_name)
                    tar_info.type = tarfile.DIRTYPE
                    tar_info.mode = 0o755
                    tar.addfile(tar_info)
                    continue

                total_uncompressed += zip_info.file_size
                if total_uncompressed > MAX_ARCHIVE_BYTES:
                    raise DeploymentValidationError(
                        "ZIP archive is too large after extraction.",
                        stage="archive_validation",
                        details={"max_bytes": MAX_ARCHIVE_BYTES},
                    )

                file_data = zipf.read(zip_info.filename)
                tar_info = tarfile.TarInfo(name=member_name)
                tar_info.size = len(file_data)
                tar_info.mode = 0o644
                tar.addfile(tar_info, io.BytesIO(file_data))

    tar_stream.seek(0)
    return merge_tar_streams(tar_stream)
