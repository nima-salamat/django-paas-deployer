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

from core.global_settings.config import MIRROR_DOCKER


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
        return str(override).strip()
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
        entry_point_override = (config.entry_point or "").strip() or None
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

    if entry_point_override and not use_celery:
        web_cmd = entry_point_override
        packages = _runtime_pip_packages(
            platform="django",
            server_type=resolved_server_type,
            use_celery=False,
            use_beat=False,
            web_cmd=web_cmd,
        )
        rendered = _inject_pip_install(rendered, packages)
        return _replace_cmd(rendered, web_cmd)

    workers = _worker_count_from_config(config)
    web_cmd = (
        entry_point_override
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

def _render_flask_or_python(platform, dockerfile_template, tar_stream, config, logger):
    server_type_override = entry_point_override = None
    use_celery = use_beat = False
    if config is not None:
        server_type_override = config.server_type or None
        entry_point_override = (config.entry_point or "").strip() or None
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

    if entry_point_override and not use_celery:
        web_cmd = entry_point_override
        packages = _runtime_pip_packages(
            platform=platform,
            server_type=resolved_type,
            use_celery=False,
            use_beat=False,
            web_cmd=web_cmd,
        )
        rendered = _inject_pip_install(rendered, packages)
        return _replace_cmd(rendered, web_cmd)

    workers = _worker_count_from_config(config)
    web_cmd = (
        entry_point_override
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
        entry_point_override = (config.entry_point or "").strip() or None

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

    if project_cfg and project_cfg.install_command:
        rendered = _swap_npm_install(rendered, project_cfg.install_command)

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
        if logger:
            logger.info(
                "dockerfile_generation",
                f"Using detected start command: {project_cfg.start_command}",
                progress=15,
                details={
                    "start_command": project_cfg.start_command,
                    "build_dir": build_dir,
                    "framework": getattr(project_cfg, "framework", None),
                },
            )
        return _replace_cmd(rendered, project_cfg.start_command)

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
    Resolve Apache DocumentRoot relative to ``/var/www/html``.

    Returns a relative path such as ``""`` (meaning ``/var/www/html``),
    ``"MyApp"``, or ``"MyApp/public"``.  Never returns an absolute path.

    Priority
    --------
    1. Explicit user override (Deploy.config document_root / DOCUMENT_ROOT)
    2. Laravel / Symfony style: ``…/public/index.php`` (shallowest)
    3. Plain PHP: shallowest ``index.php``
    4. Platform inspect hint (``static_dir`` / ``document_root``)
    5. Single top-level archive directory
    6. Fallback: ``""`` → ``/var/www/html``

    Handles archives that unpack into a single top-level directory
    (common for GitHub release zips) without hard-coding any project name.
    """
    def _clean_rel(path: str) -> str:
        p = (path or "").replace("\\", "/").strip().lstrip("./").rstrip("/")
        if p in {"", ".", ".."} or p.startswith("/") or "/../" in f"/{p}/":
            return ""
        return p

    if user_override and str(user_override).strip():
        return _clean_rel(str(user_override))

    # project_cfg paths (e.g. static_dir="public") are relative to the
    # *application* root. Archives often wrap that root in a single
    # top-level directory, so resolve against the tar layout first.

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
    top_level = sorted({n.split("/", 1)[0] for n in names if n})
    single_prefix = ""
    if len(top_level) == 1:
        only = top_level[0]
        if any(n.startswith(only + "/") for n in names):
            single_prefix = only

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
        return _clean_rel(rel)

    if project_cfg is not None:
        sd = getattr(project_cfg, "static_dir", None) or getattr(
            project_cfg, "document_root", None
        )
        if sd and str(sd).strip():
            sd_rel = _clean_rel(str(sd))
            if single_prefix and sd_rel and not sd_rel.startswith(single_prefix):
                return _clean_rel(f"{single_prefix}/{sd_rel}")
            return sd_rel or single_prefix

    if single_prefix:
        return single_prefix

    return ""


def _apply_php_document_root(dockerfile: str, document_root_rel: str) -> str:
    """
    Set ``APACHE_DOCUMENT_ROOT`` and rewrite Apache vhost / conf paths.

    ``document_root_rel`` is relative to ``/var/www/html`` (may be empty).
    """
    rel = (document_root_rel or "").replace("\\", "/").strip().lstrip("./").rstrip("/")
    if rel in {".", ".."} or rel.startswith("/") or "/../" in f"/{rel}/":
        rel = ""
    absolute = f"/var/www/html/{rel}" if rel else "/var/www/html"

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

    # Official php:*-apache images honour APACHE_DOCUMENT_ROOT only when
    # conf files are rewritten. Always inject the sed block once.
    if "sites-available" in dockerfile and "APACHE_DOCUMENT_ROOT" in dockerfile:
        return dockerfile

    sed_block = (
        "RUN sed -ri -e 's!/var/www/html!${APACHE_DOCUMENT_ROOT}!g' "
        "/etc/apache2/sites-available/*.conf \\\n"
        "    && sed -ri -e 's!/var/www/!${APACHE_DOCUMENT_ROOT}!g' "
        "/etc/apache2/apache2.conf /etc/apache2/conf-available/*.conf \\\n"
        "    && sed -i 's/AllowOverride None/AllowOverride All/g' "
        "/etc/apache2/apache2.conf"
    )

    if re.search(r"^COPY\s+\.\s+/var/www/html/?\s*$", dockerfile, re.MULTILINE):
        dockerfile = re.sub(
            r"^(COPY\s+\.\s+/var/www/html/?\s*)$",
            rf"\1\n\n{sed_block}",
            dockerfile,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        dockerfile = dockerfile.rstrip() + "\n\n" + sed_block + "\n"

    return dockerfile


def _render_php(dockerfile_template, tar_stream, config, logger):
    entry_point_override = None
    if config is not None:
        entry_point_override = (config.entry_point or "").strip() or None

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

    doc_root_rel = _detect_php_document_root(
        tar_stream,
        user_override=user_doc_root,
        project_cfg=project_cfg,
    )

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
                "platform": "php",
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
    return rendered


def _render_generic(platform, dockerfile_template, tar_stream, config, logger):
    entry_point_override = None
    if config is not None:
        entry_point_override = (config.entry_point or "").strip() or None
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
        elif platform in ("php", "laravel"):
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

