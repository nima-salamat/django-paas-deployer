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
) -> str:
    """Pick the directory that `npm run build` will actually produce."""
    if project_cfg is not None:
        for attr in ("build_dir", "output_dir", "static_dir", "publish_dir"):
            val = getattr(project_cfg, attr, None)
            if val and str(val).strip():
                d = str(val).strip().lstrip("./").rstrip("/")
                if d:
                    return d
        fw = getattr(project_cfg, "framework", None)
        return _default_spa_build_dir(platform, fw)

    # Fallback: inspect package.json inside the tar for CRA vs Vite signals
    fw = (info or {}).get("framework")
    if tar_stream is not None:
        try:
            import json
            import tarfile as _tf
            tar_stream.seek(0)
            with _tf.open(fileobj=tar_stream, mode="r:*") as tar:
                for member in tar.getmembers():
                    if not member.name.endswith("package.json"):
                        continue
                    if member.name.count("/") > 1:
                        continue
                    fobj = tar.extractfile(member)
                    if not fobj:
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
                        tar_stream.seek(0)
                        return "build"
                    if "vite" in deps or "@vitejs/plugin-react" in deps:
                        tar_stream.seek(0)
                        return "dist"
                    break
            tar_stream.seek(0)
        except Exception:
            try:
                tar_stream.seek(0)
            except Exception:
                pass

    return _default_spa_build_dir(platform, fw)


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
    Rewrite every
        COPY --from=builder /app/<old> ...
    (and the common `/app/build` / `/app/dist` variants) so the stage-2
    COPY matches the directory that the builder actually produced.
    """
    build_dir = build_dir.strip().lstrip("./").rstrip("/")
    if not build_dir:
        return dockerfile

    # Match COPY --from=builder  /app/SOMETHING  DEST
    # SOMETHING may be "build", "dist", "dist/my-app", etc.
    pattern = re.compile(
        r"(COPY\s+--from=builder\s+)/app/([^\s]+)",
        re.IGNORECASE,
    )

    def _sub(match: re.Match) -> str:
        prefix = match.group(1)
        old_path = match.group(2).rstrip("/")
        # Only rewrite the well-known static-output paths (or anything under them)
        first = old_path.split("/", 1)[0]
        if first in ("build", "dist", "out", "public", "www"):
            return f"{prefix}/app/{build_dir}"
        return match.group(0)

    return pattern.sub(_sub, dockerfile)


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

    build_dir = _resolve_spa_build_dir(platform, project_cfg, info, tar_stream=tar_stream)

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
        if logger and rendered != before:
            logger.info(
                "dockerfile_generation",
                f"SPA build output path set to /app/{build_dir}",
                progress=14,
                details={"build_dir": build_dir, "platform": platform},
            )

        # Explicit user entry_point may still override the final CMD
        if entry_point_override:
            if logger:
                logger.info(
                    "dockerfile_generation",
                    f"Using user entry_point override: {entry_point_override}",
                    progress=15,
                )
            return _replace_cmd(rendered, entry_point_override)

        # Keep nginx CMD – do not swap in "npx serve …" which breaks the
        # multi-stage image (no node runtime in the final nginx stage).
        if logger:
            logger.info(
                "dockerfile_generation",
                "Nginx SPA template – keeping nginx CMD, build_dir corrected.",
                progress=15,
                details={"build_dir": build_dir},
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


def _render_php(dockerfile_template, tar_stream, config, logger):
    entry_point_override = None
    if config is not None:
        entry_point_override = (config.entry_point or "").strip() or None
    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)
    if entry_point_override:
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
            return _render_django(dockerfile_template, tar_stream, config, logger)
        if platform in ("flask", "python", "fastapi"):
            return _render_flask_or_python(
                platform if platform != "fastapi" else "python",
                dockerfile_template, tar_stream, config, logger
            )
        if platform in (
            "nodejs", "nextjs", "react", "vuejs", "vue", "angular",
            "vite", "express",
        ):
            return _render_node_family(
                platform, dockerfile_template, tar_stream, config, logger
            )
        if platform in ("php", "laravel"):
            return _render_php(dockerfile_template, tar_stream, config, logger)
        if platform == "go":
            return _render_generic(platform, dockerfile_template, tar_stream, config, logger)
        return _render_generic(
            platform, dockerfile_template, tar_stream, config, logger
        )
