from __future__ import annotations

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
    """
    Packages the deployer injects via `pip install` so the image runs even if
    the project's requirements.txt is incomplete.

    Rules:
      - Django / Flask / Python always get gunicorn
      - ASGI / uvicorn in command → uvicorn[standard]
      - celery flag → celery + supervisor
      - celery_beat flag → django-celery-beat
    """
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

    # de-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for p in packages:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    return ordered


def _inject_pip_install(dockerfile: str, packages: list[str]) -> str:
    """
    Append a RUN pip install for runtime packages.

    Uses `|| true` only as last resort so a mirror blip does not hard-fail
    the whole build when packages are already present from requirements.txt.
    """
    if not packages:
        return dockerfile
    pkgs = " ".join(packages)
    block = (
        "\n# --- Runtime deps injected by deployer (from Deploy.config flags) ---\n"
        f"RUN pip install --no-cache-dir {pkgs}\n"
    )
    # Prefer inserting after the last existing pip install line
    matches = list(re.finditer(r"^RUN pip install[^\n]*$", dockerfile, flags=re.MULTILINE))
    if matches:
        last = matches[-1]
        return dockerfile[: last.end()] + "\n" + block.strip() + dockerfile[last.end() :]
    return dockerfile.rstrip() + "\n" + block


def _strip_cmd_entrypoint(dockerfile: str) -> str:
    cleaned = re.sub(r"^\s*(CMD|ENTRYPOINT)\s+.*$", "", dockerfile, flags=re.MULTILINE)
    return cleaned.rstrip()


def _replace_cmd(dockerfile: str, new_cmd: str) -> str:
    cleaned = _strip_cmd_entrypoint(dockerfile)
    parts = new_cmd.split()
    json_array = "[" + ", ".join(f'"{p}"' for p in parts) + "]"
    return cleaned + f"\n\nCMD {json_array}\n"


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
    ).strip()
    supervisor_conf_escaped = supervisor_conf.replace("'", "'\\''")

    lines = [
        "",
        "# --- Supervisor process manager (injected by deployer) ---",
        "RUN mkdir -p /etc/supervisor/conf.d /var/log/supervisor",
        f"RUN printf '%s\\n' '{supervisor_conf_escaped}' > /etc/supervisor/conf.d/app.conf",
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

    # Custom entry point without celery → single process CMD
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
    entry_point_override = None
    if config is not None:
        entry_point_override = (config.entry_point or "").strip() or None
    info = resolve_node_entrypoint(tar_stream)
    if logger:
        logger.info(
            "entrypoint_detection",
            f"Node package detected (framework={info.get('framework')}).",
            progress=12,
            details=info,
        )
    rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)
    if entry_point_override:
        return _replace_cmd(rendered, entry_point_override)
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
        if platform in ("flask", "python"):
            return _render_flask_or_python(
                platform, dockerfile_template, tar_stream, config, logger
            )
        if platform in ("nodejs", "nextjs", "react", "vuejs", "vue", "angular"):
            return _render_node_family(
                platform, dockerfile_template, tar_stream, config, logger
            )
        if platform == "php":
            return _render_php(dockerfile_template, tar_stream, config, logger)
        return _render_generic(
            platform, dockerfile_template, tar_stream, config, logger
        )
