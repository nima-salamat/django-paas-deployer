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

def _django_web_command(module: str, server_type: str) -> str:
    if server_type == "asgi":
        return (
            f"uvicorn {module}:application "
            f"--host 0.0.0.0 --port 8000 --workers 2"
        )
    return (
        f"gunicorn {module}:application "
        f"--bind 0.0.0.0:8000 --workers 3 --timeout 60"
    )


def _flask_web_command(module: str, callable_name: str, server_type: str) -> str:
    target = f"{module}:{callable_name.rstrip('()')}"
    if server_type == "asgi" or "fastapi" in module.lower():
        return (
            f"gunicorn {target} "
            f"--worker-class uvicorn.workers.UvicornWorker "
            f"--bind 0.0.0.0:8000 --workers 2 --timeout 60"
        )
    return f"gunicorn {target} --bind 0.0.0.0:8000 --workers 3 --timeout 60"


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
command=celery -A {celery_app} worker --loglevel=info --concurrency=2
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


def _build_supervisor_addon(web_cmd: str, celery_app: str, celery_beat: bool) -> str:
    beat_section = (
        _SUPERVISOR_BEAT_SECTION.format(celery_app=celery_app) if celery_beat else ""
    )
    supervisor_conf = _SUPERVISOR_CONF_TEMPLATE.format(
        web_cmd=web_cmd,
        celery_app=celery_app,
        beat_section=beat_section,
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

    web_cmd = (
        entry_point_override
        if entry_point_override
        else _django_web_command(module, resolved_server_type)
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
        addon = _build_supervisor_addon(web_cmd, celery_app, use_beat)
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

    web_cmd = (
        entry_point_override
        if entry_point_override
        else _flask_web_command(module, callable_name, resolved_type)
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
        addon = _build_supervisor_addon(web_cmd, celery_app, use_beat)
        rendered = _strip_cmd_entrypoint(rendered)
        return rendered + "\n" + addon

    rendered = _replace_cmd(rendered, web_cmd)
    if platform == "flask" and "FLASK_APP" not in rendered:
        rendered = rendered.replace(
            "WORKDIR /app",
            f"WORKDIR /app\nENV FLASK_APP={module}.py\nENV FLASK_ENV=production",
        )
    return rendered


def _render_node_family(platform, dockerfile_template, tar_stream, config, logger):
    """
    Render Node/Next.js/React/Vue Dockerfiles.
    
    Priority for start_command:
    1. User-provided entry_point
    2. ProjectConfig.start_command from platforms/ detector
    3. Default template command
    """
    entry_point_override = None
    if config is not None:
        entry_point_override = (config.entry_point or "").strip() or None

    # Get ProjectConfig from platforms/ detector when available
    project_cfg = None
    try:
        from .platform_bridge import get_project_cfg
        project_cfg = get_project_cfg(config) if config else None
    except Exception:
        project_cfg = None

    info = resolve_node_entrypoint(tar_stream)
    
    if logger:
        logger.info(
            "entrypoint_detection",
            f"Node package detected (framework={info.get('framework')}).",
            progress=12,
            details={
                **(info or {}),
                "from_platforms": bool(project_cfg),
                "package_manager": getattr(project_cfg, "package_manager", None) if project_cfg else None,
                "start_command": getattr(project_cfg, "start_command", None) if project_cfg else None,
                "build_dir": getattr(project_cfg, "build_dir", None) if project_cfg else None,
            },
        )

    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)

    # Apply package manager install command from platforms detector
    if project_cfg and project_cfg.install_command:
        rendered = _swap_npm_install(rendered, project_cfg.install_command)

    # User override takes highest priority
    if entry_point_override:
        return _replace_cmd(rendered, entry_point_override)

    # Use start_command from platforms detector (which includes correct build_dir)
    if project_cfg and project_cfg.start_command:
        if logger:
            logger.info(
                "dockerfile_generation",
                f"Using detected start command: {project_cfg.start_command}",
                progress=15,
                details={
                    "start_command": project_cfg.start_command,
                    "build_dir": project_cfg.build_dir,
                    "framework": project_cfg.framework,
                },
            )
        return _replace_cmd(rendered, project_cfg.start_command)

    # Fallback: use template default (shouldn't reach here if platforms/ works)
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