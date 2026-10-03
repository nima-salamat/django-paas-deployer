import re
import tarfile
import json

from .exceptions import DeploymentValidationError


def django_read_settings_module_from_tar(tar: tarfile.TarFile):
    """Return the DJANGO_SETTINGS_MODULE value found in manage.py, or None."""
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
            text, re.S,
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
            "Django entrypoint could not be detected. "
            "Ensure manage.py and ASGI_APPLICATION or WSGI_APPLICATION exist.",
            stage="entrypoint_detection",
            details={"platform": "django"},
        )
    return entrypoint


def resolve_django_entrypoint(tar_stream, *, server_type: str | None = None) -> dict:
    server_type_clean = (server_type or "").strip().lower() or None
    if server_type_clean not in (None, "asgi", "wsgi"):
        raise DeploymentValidationError(
            f"server_type must be 'asgi', 'wsgi', or omitted; got '{server_type}'.",
            stage="entrypoint_detection",
            details={"server_type": server_type},
        )
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        detected = django_find_entrypoint_from_settings(tar)
    tar_stream.seek(0)
    if detected is None:
        raise DeploymentValidationError(
            "Django entrypoint could not be detected. "
            "Ensure manage.py and ASGI_APPLICATION or WSGI_APPLICATION exist.",
            stage="entrypoint_detection",
            details={"platform": "django", "server_type_override": server_type_clean},
        )
    if server_type_clean is not None and server_type_clean != detected["type"]:
        return {"type": server_type_clean, "module": detected["module"], "override": True}
    return {"type": detected["type"], "module": detected["module"], "override": False}



def resolve_python_runtime_context(names, module: str | None) -> dict:
    """Resolve a Python import target and source root consistently for runtime.

    The build context is post-flatten. This handles:
      src/app/main.py              -> app.main + source_root=src
      backend/src/app/main.py      -> app.main + source_root=backend/src
      app/main.py                  -> app.main + source_root=''
      Repo/src/app/main.py         -> app.main + source_root=src
    """
    original_names = _archive_names_from_sequence(names)
    normalized, wrapper = _flatten_runtime_names(original_names)
    module = str(module or '').strip().strip('.')
    parts = [part for part in module.split('.') if part]

    if wrapper and parts and parts[0] == wrapper:
        parts = parts[1:]
        module = '.'.join(parts)

    def exists(path_parts: list[str]) -> bool:
        if not path_parts:
            return False
        path = '/'.join(path_parts)
        return f'{path}.py' in normalized or f'{path}/__init__.py' in normalized

    if not parts:
        return {'module': '', 'source_root': '', 'working_directory': '/app'}

    # Detector returned a full filesystem path as a dotted module.
    if exists(parts):
        best = None
        for cut in range(1, len(parts)):
            prefix = '/'.join(parts[:cut])
            remainder = parts[cut:]
            if f'{prefix}/__init__.py' in normalized:
                break
            if exists(parts):
                best = (prefix, '.'.join(remainder))
        if best:
            source_root, runtime_module = best
            return {
                'module': runtime_module,
                'source_root': source_root,
                'working_directory': f'/app/{source_root}',
            }

    # Detector returned an import package without its filesystem source root.
    module_path = '/'.join(parts)
    candidates: list[str] = []
    for name in normalized:
        if not (name.endswith('.py') or name.endswith('/__init__.py')):
            continue
        parent = name.rsplit('/', 1)[0] if '/' in name else ''
        comps = parent.split('/') if parent else []
        for cut in range(1, len(comps) + 1):
            root = '/'.join(comps[:cut])
            if (f'{root}/{module_path}.py' in normalized or
                    f'{root}/{module_path}/__init__.py' in normalized):
                candidates.append(root)
    if candidates:
        source_root = sorted(candidates, key=lambda x: (x.count('/'), len(x), x))[0]
        return {
            'module': module,
            'source_root': source_root,
            'working_directory': f'/app/{source_root}',
        }

    return {
        'module': module,
        'source_root': '',
        'working_directory': '/app',
    }


def _fastapi_pyproject_entrypoint(tar_stream) -> dict | None:
    """Read [tool.fastapi].entrypoint from pyproject.toml when configured."""
    tar_stream.seek(0)
    try:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        with tarfile.open(fileobj=tar_stream, mode='r:*') as tar:
            names = [m.name.replace('\\', '/').lstrip('./') for m in tar.getmembers()]
            for member in tar.getmembers():
                if not member.isfile() or member.name.replace('\\', '/').split('/')[-1].lower() != 'pyproject.toml':
                    continue
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                try:
                    data = tomllib.loads(file_obj.read().decode('utf-8', errors='ignore'))
                except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                    continue
                value = ((data.get('tool') or {}).get('fastapi') or {}).get('entrypoint')
                if not isinstance(value, str):
                    continue
                raw = value.strip()
                if not _FASTAPI_IMPORT_TARGET_RE.fullmatch(raw):
                    continue
                module, callable_name = raw.rsplit(':', 1)
                return {
                    'entrypoint': raw,
                    'module': module,
                    'callable': callable_name,
                    'source': 'pyproject.toml',
                    'pyproject_path': member.name.replace('\\', '/'),
                }
    finally:
        tar_stream.seek(0)
    return None


def resolve_fastapi_entrypoint(tar_stream) -> dict | None:
    """Resolve a concrete FastAPI ASGI target from the deployment archive."""
    configured = _fastapi_pyproject_entrypoint(tar_stream)
    if configured:
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode='r:*') as tar:
            names = [m.name.replace('\\', '/').lstrip('./') for m in tar.getmembers()]
        context = resolve_python_runtime_context(names, configured['module'])
        return {
            'type': 'asgi',
            'module': context['module'],
            'callable': configured['callable'],
            'priority': 1000,
            'detected': True,
            'source': configured['source'],
            'source_root': context['source_root'],
            'working_directory': context['working_directory'],
            'entrypoint': f"{context['module']}:{configured['callable']}",
            'pyproject_path': configured['pyproject_path'],
        }

    candidates: list[dict] = []
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode='r:*') as tar:
            archive_names = [m.name.replace('\\', '/').lstrip('./') for m in tar.getmembers()]
            members = [
                m for m in tar.getmembers()
                if m.isfile()
                and m.name.replace('\\', '/').lower().endswith('.py')
                and m.name.count('/') <= 8
            ]
            members.sort(key=lambda m: (
                {'main.py': 0, 'app.py': 1, 'server.py': 2, 'api.py': 3}.get(
                    m.name.rsplit('/', 1)[-1].lower(), 10
                ),
                m.name.count('/'),
                m.name,
            ))
            for member in members:
                name = member.name.replace('\\', '/')
                lower = name.lower()
                if any(part in lower.split('/') for part in ('tests', 'test', '__pycache__', 'migrations')):
                    continue
                if lower.rsplit('/', 1)[-1].startswith('test_'):
                    continue
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                text = file_obj.read().decode('utf-8', errors='ignore')
                if not (re.search(r'\bFastAPI\s*\(', text) or re.search(r'\bfastapi\.FastAPI\s*\(', text)):
                    continue
                module = name.rsplit('.', 1)[0].lstrip('./').replace('/', '.')
                context = resolve_python_runtime_context(archive_names, module)
                for match in re.finditer(
                    r'(?P<callable>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:fastapi\.)?FastAPI\s*\(',
                    text,
                ):
                    callable_name = match.group('callable')
                    name_rank = {'app': 100, 'application': 90, 'api': 80}.get(callable_name, 70)
                    file_rank = {'main.py': 30, 'app.py': 24, 'server.py': 18, 'api.py': 16}.get(
                        name.rsplit('/', 1)[-1].lower(), 0
                    )
                    candidates.append({
                        'type': 'asgi',
                        'module': context['module'],
                        'callable': callable_name,
                        'priority': name_rank + file_rank - name.count('/'),
                        'detected': True,
                        'source': 'source_scan',
                        'source_root': context['source_root'],
                        'working_directory': context['working_directory'],
                        'entrypoint': f"{context['module']}:{callable_name}",
                    })
                    break
    finally:
        tar_stream.seek(0)

    if not candidates:
        return {
            'type': 'asgi',
            'module': None,
            'callable': None,
            'detected': False,
            'override': False,
        }
    return max(candidates, key=lambda c: c['priority'])

def resolve_flask_entrypoint(tar_stream, *, server_type: str | None = None) -> dict:
    """Detect Flask / FastAPI / create_app entrypoint."""
    server_type_clean = (server_type or "").strip().lower() or None
    if server_type_clean not in (None, "asgi", "wsgi"):
        raise DeploymentValidationError(
            f"server_type must be 'asgi', 'wsgi', or omitted; got '{server_type}'.",
            stage="entrypoint_detection",
            details={"server_type": server_type},
        )
    candidates: list[dict] = []
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.name.endswith(".py") or member.name.count("/") > 2:
                continue
            if any(skip in member.name for skip in ("test_", "tests/", "__pycache__", "migrations/")):
                continue
            file_obj = tar.extractfile(member)
            if not file_obj:
                continue
            text = file_obj.read().decode("utf-8", errors="ignore")
            if re.search(r"\b(FastAPI|Starlette)\s*\(", text):
                for name in ("app", "application", "api"):
                    if re.search(rf"\b{name}\s*=\s*(FastAPI|Starlette)\s*\(", text):
                        module = member.name.rsplit(".", 1)[0].replace("/", ".")
                        if module.startswith("./"):
                            module = module[2:]
                        candidates.append({"type": "asgi", "module": module, "callable": name, "priority": 10})
                        break
            if re.search(r"\bFlask\s*\(", text):
                for name in ("app", "application"):
                    if re.search(rf"\b{name}\s*=\s*Flask\s*\(", text):
                        module = member.name.rsplit(".", 1)[0].replace("/", ".")
                        if module.startswith("./"):
                            module = module[2:]
                        candidates.append({"type": "wsgi", "module": module, "callable": name, "priority": 5})
                        break
                if re.search(r"def\s+create_app\s*\(", text):
                    module = member.name.rsplit(".", 1)[0].replace("/", ".")
                    if module.startswith("./"):
                        module = module[2:]
                    candidates.append({"type": "wsgi", "module": module, "callable": "create_app()", "priority": 4})
            if re.search(r"\bapplication\s*=\s*", text) and "wsgi" in member.name.lower():
                module = member.name.rsplit(".", 1)[0].replace("/", ".")
                candidates.append({"type": "wsgi", "module": module, "callable": "application", "priority": 3})
    tar_stream.seek(0)
    if not candidates:
        return {
            "type": server_type_clean or "wsgi",
            "module": "app",
            "callable": "app",
            "override": bool(server_type_clean),
            "detected": False,
        }
    best = max(candidates, key=lambda c: c["priority"])
    if server_type_clean and server_type_clean != best["type"]:
        best = {**best, "type": server_type_clean, "override": True}
    else:
        best["override"] = False
        best["detected"] = True
    return best


def resolve_python_entrypoint(tar_stream, *, server_type: str | None = None) -> dict:
    return resolve_flask_entrypoint(tar_stream, server_type=server_type)


def resolve_node_entrypoint(tar_stream) -> dict:
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        for member in tar.getmembers():
            if member.name.endswith("package.json") and member.name.count("/") <= 1:
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                try:
                    pkg = json.loads(file_obj.read().decode("utf-8", errors="ignore"))
                except Exception:
                    continue
                scripts = pkg.get("scripts") or {}
                start = scripts.get("start") or scripts.get("serve") or scripts.get("dev")
                main = pkg.get("main") or "index.js"
                return {
                    "start_script": start,
                    "main": main,
                    "has_build": "build" in scripts,
                    "framework": _detect_node_framework(pkg),
                }
    tar_stream.seek(0)
    return {"start_script": None, "main": "index.js", "has_build": False, "framework": "node"}


def _detect_node_framework(pkg: dict) -> str:
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    if "next" in deps:
        return "nextjs"
    if "nuxt" in deps:
        return "nuxt"
    if "react-scripts" in deps or "react" in deps:
        return "react"
    if "@angular/core" in deps:
        return "angular"
    if "vue" in deps or "@vue/cli-service" in deps:
        return "vue"
    if "express" in deps:
        return "express"
    if "fastify" in deps:
        return "fastify"
    if "vite" in deps:
        return "vite"
    return "node"


# Aligned with platforms/ plugins + DockerfileGenerator routes
PLATFORMS_REQUIRING_REQUIREMENTS_TXT = frozenset({
    "django", "python", "flask", "fastapi",
})

PYTHON_DEPENDENCY_MARKERS = frozenset({
    "requirements.txt", "pyproject.toml", "Pipfile",
})

PLATFORMS_REQUIRING_PACKAGE_JSON = frozenset({
    "nodejs", "nextjs", "react", "vuejs", "vue", "angular",
    "vite", "express",
})


def check_requirements_txt(tar_stream, *, platform: str) -> None:
    """Validate that a Python deployment contains a supported dependency manifest.

    Older code required requirements.txt for every Python-family project, which
    rejected valid Poetry and Pipenv applications before Docker build started.
    """
    if platform not in PLATFORMS_REQUIRING_REQUIREMENTS_TXT:
        return
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            names = [n.replace("\\", "/") for n in tar.getnames()]
    finally:
        tar_stream.seek(0)
    found = [
        n for n in names
        if any(n == marker or n.endswith("/" + marker) for marker in PYTHON_DEPENDENCY_MARKERS)
    ]
    if not found:
        raise DeploymentValidationError(
            "No supported Python dependency manifest was found. Add requirements.txt, pyproject.toml, or Pipfile.",
            stage="requirements_check",
            details={"platform": platform, "accepted": sorted(PYTHON_DEPENDENCY_MARKERS)},
        )


def check_package_json(tar_stream, *, platform: str) -> None:
    if platform not in PLATFORMS_REQUIRING_PACKAGE_JSON:
        return
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            names = tar.getnames()
    finally:
        tar_stream.seek(0)
    found = [n for n in names if n.endswith("package.json")]
    if not found:
        raise DeploymentValidationError(
            "package.json not found in the deployment archive. "
            "A package.json file is required for Node-based platforms.",
            stage="package_json_check",
            details={"platform": platform},
        )

)

def resolve_fastapi_entrypoint(tar_stream) -> dict | None:
    """Resolve a concrete FastAPI ASGI target from the deployment archive."""
    configured = _fastapi_pyproject_entrypoint(tar_stream)
    if configured:
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            names = [m.name.replace("\\", "/").lstrip("./") for m in tar.getmembers()]
        context = resolve_python_runtime_context(names, configured["module"])
        target = f'{context["module"]}:{configured["callable"]}'
        return {
            "type": "asgi",
            "module": context["module"],
            "callable": configured["callable"],
            "priority": 1000,
            "detected": True,
            "source": configured["source"],
            "source_root": context["source_root"],
            "working_directory": context["working_directory"],
            "entrypoint": target,
            "pyproject_path": configured["pyproject_path"],
        }
    candidates: list[dict] = []
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            members = [
                m for m in tar.getmembers()
                if m.isfile()
                and m.name.replace("\\", "/").lower().endswith(".py")
                and m.name.count("/") <= 5
            ]
            members.sort(
                key=lambda m: (
                    {
                        "main.py": 0,
                        "app.py": 1,
                        "server.py": 2,
                        "api.py": 3,
                    }.get(m.name.rsplit("/", 1)[-1].lower(), 10),
                    m.name.count("/"),
                    m.name,
                )
            )
            for member in members:
                name = member.name.replace("\\", "/")
                lower = name.lower()
                if any(
                    part in lower.split("/")
                    for part in ("tests", "test", "__pycache__", "migrations")
                ) or lower.rsplit("/", 1)[-1].startswith("test_"):
                    continue
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                text = file_obj.read().decode("utf-8", errors="ignore")
                if not (
                    re.search(r"\bFastAPI\s*\(", text)
                    or re.search(r"\bfastapi\.FastAPI\s*\(", text)
                ):
                    continue

                module = name.rsplit(".", 1)[0].lstrip("./").replace("/", ".")
                for match in re.finditer(
                    r"(?P<callable>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:fastapi\.)?FastAPI\s*\(",
                    text,
                ):
                    callable_name = match.group("callable")
                    name_rank = {"app": 100, "application": 90, "api": 80}.get(callable_name, 70)
                    file_rank = {
                        "main.py": 30,
                        "app.py": 24,
                        "server.py": 18,
                        "api.py": 16,
                    }.get(name.rsplit("/", 1)[-1].lower(), 0)
                    candidates.append({
                        "type": "asgi",
                        "module": module,
                        "callable": callable_name,
                        "priority": name_rank + file_rank - name.count("/"),
                        "detected": True,
                    })
                    break
    finally:
        tar_stream.seek(0)

    if not candidates:
        return {
            "type": "asgi",
            "module": None,
            "callable": None,
            "detected": False,
            "override": False,
        }
    return max(candidates, key=lambda c: c["priority"])


def resolve_flask_entrypoint(tar_stream, *, server_type: str | None = None) -> dict:
    """Detect Flask / FastAPI / create_app entrypoint."""
    server_type_clean = (server_type or "").strip().lower() or None
    if server_type_clean not in (None, "asgi", "wsgi"):
        raise DeploymentValidationError(
            f"server_type must be 'asgi', 'wsgi', or omitted; got '{server_type}'.",
            stage="entrypoint_detection",
            details={"server_type": server_type},
        )
    candidates: list[dict] = []
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.name.endswith(".py") or member.name.count("/") > 2:
                continue
            if any(skip in member.name for skip in ("test_", "tests/", "__pycache__", "migrations/")):
                continue
            file_obj = tar.extractfile(member)
            if not file_obj:
                continue
            text = file_obj.read().decode("utf-8", errors="ignore")
            if re.search(r"\b(FastAPI|Starlette)\s*\(", text):
                for name in ("app", "application", "api"):
                    if re.search(rf"\b{name}\s*=\s*(FastAPI|Starlette)\s*\(", text):
                        module = member.name.rsplit(".", 1)[0].replace("/", ".")
                        if module.startswith("./"):
                            module = module[2:]
                        candidates.append({"type": "asgi", "module": module, "callable": name, "priority": 10})
                        break
            if re.search(r"\bFlask\s*\(", text):
                for name in ("app", "application"):
                    if re.search(rf"\b{name}\s*=\s*Flask\s*\(", text):
                        module = member.name.rsplit(".", 1)[0].replace("/", ".")
                        if module.startswith("./"):
                            module = module[2:]
                        candidates.append({"type": "wsgi", "module": module, "callable": name, "priority": 5})
                        break
                if re.search(r"def\s+create_app\s*\(", text):
                    module = member.name.rsplit(".", 1)[0].replace("/", ".")
                    if module.startswith("./"):
                        module = module[2:]
                    candidates.append({"type": "wsgi", "module": module, "callable": "create_app()", "priority": 4})
            if re.search(r"\bapplication\s*=\s*", text) and "wsgi" in member.name.lower():
                module = member.name.rsplit(".", 1)[0].replace("/", ".")
                candidates.append({"type": "wsgi", "module": module, "callable": "application", "priority": 3})
    tar_stream.seek(0)
    if not candidates:
        return {
            "type": server_type_clean or "wsgi",
            "module": "app",
            "callable": "app",
            "override": bool(server_type_clean),
            "detected": False,
        }
    best = max(candidates, key=lambda c: c["priority"])
    if server_type_clean and server_type_clean != best["type"]:
        best = {**best, "type": server_type_clean, "override": True}
    else:
        best["override"] = False
        best["detected"] = True
    return best


def resolve_python_entrypoint(tar_stream, *, server_type: str | None = None) -> dict:
    return resolve_flask_entrypoint(tar_stream, server_type=server_type)


def resolve_node_entrypoint(tar_stream) -> dict:
    tar_stream.seek(0)
    with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
        for member in tar.getmembers():
            if member.name.endswith("package.json") and member.name.count("/") <= 1:
                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                try:
                    pkg = json.loads(file_obj.read().decode("utf-8", errors="ignore"))
                except Exception:
                    continue
                scripts = pkg.get("scripts") or {}
                start = scripts.get("start") or scripts.get("serve") or scripts.get("dev")
                main = pkg.get("main") or "index.js"
                return {
                    "start_script": start,
                    "main": main,
                    "has_build": "build" in scripts,
                    "framework": _detect_node_framework(pkg),
                }
    tar_stream.seek(0)
    return {"start_script": None, "main": "index.js", "has_build": False, "framework": "node"}


def _detect_node_framework(pkg: dict) -> str:
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    if "next" in deps:
        return "nextjs"
    if "nuxt" in deps:
        return "nuxt"
    if "react-scripts" in deps or "react" in deps:
        return "react"
    if "@angular/core" in deps:
        return "angular"
    if "vue" in deps or "@vue/cli-service" in deps:
        return "vue"
    if "express" in deps:
        return "express"
    if "fastify" in deps:
        return "fastify"
    if "vite" in deps:
        return "vite"
    return "node"


# Aligned with platforms/ plugins + DockerfileGenerator routes
PLATFORMS_REQUIRING_REQUIREMENTS_TXT = frozenset({
    "django", "python", "flask", "fastapi",
})

PYTHON_DEPENDENCY_MARKERS = frozenset({
    "requirements.txt", "pyproject.toml", "Pipfile",
})

PLATFORMS_REQUIRING_PACKAGE_JSON = frozenset({
    "nodejs", "nextjs", "react", "vuejs", "vue", "angular",
    "vite", "express",
})


def check_requirements_txt(tar_stream, *, platform: str) -> None:
    """Validate that a Python deployment contains a supported dependency manifest.

    Older code required requirements.txt for every Python-family project, which
    rejected valid Poetry and Pipenv applications before Docker build started.
    """
    if platform not in PLATFORMS_REQUIRING_REQUIREMENTS_TXT:
        return
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            names = [n.replace("\\", "/") for n in tar.getnames()]
    finally:
        tar_stream.seek(0)
    found = [
        n for n in names
        if any(n == marker or n.endswith("/" + marker) for marker in PYTHON_DEPENDENCY_MARKERS)
    ]
    if not found:
        raise DeploymentValidationError(
            "No supported Python dependency manifest was found. Add requirements.txt, pyproject.toml, or Pipfile.",
            stage="requirements_check",
            details={"platform": platform, "accepted": sorted(PYTHON_DEPENDENCY_MARKERS)},
        )


def check_package_json(tar_stream, *, platform: str) -> None:
    if platform not in PLATFORMS_REQUIRING_PACKAGE_JSON:
        return
    tar_stream.seek(0)
    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            names = tar.getnames()
    finally:
        tar_stream.seek(0)
    found = [n for n in names if n.endswith("package.json")]
    if not found:
        raise DeploymentValidationError(
            "package.json not found in the deployment archive. "
            "A package.json file is required for Node-based platforms.",
            stage="package_json_check",
            details={"platform": platform},
        )
