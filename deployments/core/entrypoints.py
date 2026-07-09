import re
import tarfile

from .exceptions import DeploymentValidationError


def django_read_settings_module_from_tar(tar: tarfile.TarFile):
    for member in tar.getmembers():
        if not member.name.endswith("manage.py"):
            continue

        file_obj = tar.extractfile(member)
        if not file_obj:
            continue

        text = file_obj.read().decode("utf-8", errors="ignore")
        text = re.sub(r"#.*", "", text)
        match = re.search(
            r"os\.environ\.setdefault\s*\(\s*['\"]DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([\w\.]+)['\"]\s*\)",
            text,
            re.S,
        )
        if match:
            return match.group(1)

        match = re.search(r"DJANGO_SETTINGS_MODULE\s*=\s*['\"]([\w\.]+)['\"]", text)
        if match:
            return match.group(1)

    return None


def django_find_entrypoint_from_settings(tar: tarfile.TarFile):
    settings_module = django_read_settings_module_from_tar(tar)
    if not settings_module:
        return None

    settings_path = settings_module.replace(".", "/") + ".py"
    member = next((item for item in tar.getmembers() if item.name.endswith(settings_path)), None)
    if not member:
        return None

    file_obj = tar.extractfile(member)
    if not file_obj:
        return None

    text = file_obj.read().decode("utf-8", errors="ignore")
    patterns = (
        ("asgi", re.compile(r"(?<!\w)ASGI_APPLICATION\s*=\s*['\"]([\w\.]+)['\"]")),
        ("wsgi", re.compile(r"(?<!\w)WSGI_APPLICATION\s*=\s*['\"]([\w\.]+)['\"]")),
    )

    for entrypoint_type, pattern in patterns:
        match = pattern.search(text)
        if match:
            module = match.group(1).rsplit(".", 1)[0]
            return {"type": entrypoint_type, "module": module}

    return None


def require_django_entrypoint(tar_stream):
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        entrypoint = django_find_entrypoint_from_settings(tar)

    tar_stream.seek(0)
    if not entrypoint:
        raise DeploymentValidationError(
            "Django entrypoint could not be detected. Ensure manage.py and ASGI_APPLICATION or WSGI_APPLICATION exist.",
            stage="entrypoint_detection",
            details={"platform": "django"},
        )

    return entrypoint
