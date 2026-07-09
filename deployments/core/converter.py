import io
import os
import tarfile
import zipfile

from .exceptions import DeploymentValidationError


MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000


def _is_safe_archive_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        return False
    return normalized not in {"", ".", ".."}


def _is_zip_symlink(zip_info: zipfile.ZipInfo) -> bool:
    mode = zip_info.external_attr >> 16
    return (mode & 0o170000) == 0o120000


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
                    details={"max_members": MAX_ARCHIVE_MEMBERS, "actual_members": len(members)},
                )

            for zip_info in members:
                if zip_info.is_dir():
                    continue

                if not _is_safe_archive_name(zip_info.filename):
                    raise DeploymentValidationError(
                        "ZIP archive contains an unsafe file path.",
                        stage="archive_validation",
                        details={"filename": zip_info.filename},
                    )

                if _is_zip_symlink(zip_info):
                    raise DeploymentValidationError(
                        "ZIP archive contains symbolic links, which are not allowed.",
                        stage="archive_validation",
                        details={"filename": zip_info.filename},
                    )

                total_uncompressed += zip_info.file_size
                if total_uncompressed > MAX_ARCHIVE_BYTES:
                    raise DeploymentValidationError(
                        "ZIP archive is too large after extraction.",
                        stage="archive_validation",
                        details={"max_bytes": MAX_ARCHIVE_BYTES},
                    )

                file_data = zipf.read(zip_info.filename)
                tar_info = tarfile.TarInfo(name=zip_info.filename)
                tar_info.size = len(file_data)
                tar_info.mode = 0o644
                tar.addfile(tar_info, io.BytesIO(file_data))

    tar_stream.seek(0)
    return merge_tar_streams(tar_stream)
