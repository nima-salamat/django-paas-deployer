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


def _django_web_command(module: str, server_type: str) -> str:
    if server_type == "asgi":
        return f"uvicorn {module}:application --host 0.0.0.0 --port 8000 --workers 2"
    return f"gunicorn {module}:application --bind 0.0.0.0:8000 --workers 3 --timeout 60"


def _flask_web_command(module: str, callable_name: str, server_type: str) -> str:
    target = f"{module}:{callable_name.rstrip('()')}"
    if server_type == "asgi" or "fastapi" in module.lower():
        return (
            f"gunicorn {target} "
            f"--worker-class uvicorn.workers.UvicornWorker "
            f"--bind 0.0.0.0:8000 --workers 2 --timeout 60"
        )
    return f"gunicorn {target} --bind 0.0.0.0:8000 --workers 3 --timeout 60"


def _celery_app_name(module: str) -> str:
    return module.split(".")[0]


_SUPERVISOR_CONF_TEMPLATE = """\
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:web]
command={web_cmd}
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:worker]
command=celery -A {celery_app} worker --loglevel=info
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
{beat_section}"""

_SUPERVISOR_BEAT_SECTION = """\
[program:beat]
command=celery -A {celery_app} beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0"""


def _build_supervisor_dockerfile_addon(web_cmd: str, celery_app: str, celery_beat: bool) -> str:
    beat_section = (
        _SUPERVISOR_BEAT_SECTION.format(celery_app=celery_app) if celery_beat else ""
    )
    supervisor_conf = _SUPERVISOR_CONF_TEMPLATE.format(
        web_cmd=web_cmd, celery_app=celery_app, beat_section=beat_section,
    ).strip()
    supervisor_conf_escaped = supervisor_conf.replace("'", "'\\''")
    extra_pip = "RUN pip install --no-cache-dir supervisor"
    if "uvicorn" in web_cmd:
        extra_pip = "RUN pip install --no-cache-dir supervisor uvicorn[standard]"
    lines = [
        "",
        "# --- Supervisor setup (injected by deployer) ---",
        extra_pip,
        "RUN mkdir -p /etc/supervisor/conf.d",
        f"RUN printf '%s\\n' '{supervisor_conf_escaped}' > /etc/supervisor/conf.d/app.conf",
        "",
        'CMD ["supervisord", "-c", "/etc/supervisor/conf.d/app.conf"]',
    ]
    return "\n".join(lines)


def _replace_cmd(dockerfile: str, new_cmd: str) -> str:
    cleaned = re.sub(r"^\s*(CMD|ENTRYPOINT)\s+.*$", "", dockerfile, flags=re.MULTILINE)
    cleaned = cleaned.rstrip()
    parts = new_cmd.split()
    json_array = "[" + ", ".join(f'"{p}"' for p in parts) + "]"
    return cleaned + f"\n\nCMD {json_array}\n"


def _ensure_gunicorn_in_requirements(dockerfile: str) -> str:
    if "gunicorn" in dockerfile.lower():
        return dockerfile
    install_line = (
        'RUN pip install --no-cache-dir gunicorn uvicorn[standard] '
        '|| pip install --no-cache-dir gunicorn'
    )
    if "pip install" in dockerfile:
        return re.sub(r"(RUN pip install[^\n]+)", r"\1\n" + install_line, dockerfile, count=1)
    return dockerfile + "\n" + install_line + "\n"


def _render_django(dockerfile_template, tar_stream, config, logger):
    server_type_override = entry_point_override = None
    use_celery = use_beat = False
    if config is not None:
        server_type_override = config.server_type or None
        entry_point_override = (config.entry_point or "").strip() or None
        use_celery = bool(config.celery)
        use_beat = bool(config.celery_beat) and use_celery
    if logger:
        logger.info("entrypoint_detection", "Detecting Django ASGI/WSGI entrypoint.", progress=12)
    try:
        entrypoint = resolve_django_entrypoint(tar_stream, server_type=server_type_override)
    except DeploymentValidationError:
        raise
    except Exception as exc:
        raise DeploymentValidationError(
            "Unexpected error during entrypoint detection.",
            stage="entrypoint_detection", details={"error": str(exc)},
        ) from exc
    module = entrypoint["module"]
    resolved_server_type = entrypoint["type"]
    if logger and entrypoint.get("override"):
        logger.info("entrypoint_detection", f"server_type overridden to '{resolved_server_type}'.", progress=13,
                    details={"module": module, "server_type": resolved_server_type})
    try:
        rendered = dockerfile_template.format(module=module, MIRROR_DOCKER=MIRROR_DOCKER)
    except KeyError as exc:
        raise DeploymentValidationError(
            f"Django Dockerfile template contains an unknown placeholder: {exc.args[0] if exc.args else 'unknown'}",
            stage="dockerfile_generation", details={"module": module},
        ) from exc
    except Exception as exc:
        raise DeploymentValidationError(
            "Django Dockerfile template could not be rendered.",
            stage="dockerfile_generation", details={"module": module, "error": str(exc)},
        ) from exc
    if entry_point_override:
        return _replace_cmd(rendered, entry_point_override)
    if use_celery:
        web_cmd = _django_web_command(module, resolved_server_type)
        celery_app = _celery_app_name(module)
        addon = _build_supervisor_dockerfile_addon(web_cmd, celery_app, use_beat)
        rendered = re.sub(r"^\s*(CMD|ENTRYPOINT)\s+.*$", "", rendered, flags=re.MULTILINE).rstrip()
        return rendered + "\n" + addon
    web_cmd = _django_web_command(module, resolved_server_type)
    rendered = _replace_cmd(rendered, web_cmd)
    return _ensure_gunicorn_in_requirements(rendered)


def _render_flask_or_python(platform, dockerfile_template, tar_stream, config, logger):
    server_type_override = entry_point_override = None
    use_celery = use_beat = False
    if config is not None:
        server_type_override = config.server_type or None
        entry_point_override = (config.entry_point or "").strip() or None
        use_celery = bool(config.celery)
        use_beat = bool(config.celery_beat) and use_celery
    if logger:
        logger.info("entrypoint_detection", f"Detecting {platform} application entrypoint.", progress=12)
    entrypoint = resolve_flask_entrypoint(tar_stream, server_type=server_type_override)
    module = entrypoint.get("module", "app")
    callable_name = entrypoint.get("callable", "app")
    resolved_type = entrypoint.get("type", "wsgi")
    try:
        rendered = dockerfile_template.format(module=module, MIRROR_DOCKER=MIRROR_DOCKER)
    except Exception:
        rendered = dockerfile_template.replace("{MIRROR_DOCKER}", MIRROR_DOCKER)
    if entry_point_override:
        return _replace_cmd(rendered, entry_point_override)
    web_cmd = _flask_web_command(module, callable_name, resolved_type)
    if use_celery:
        celery_app = _celery_app_name(module)
        addon = _build_supervisor_dockerfile_addon(web_cmd, celery_app, use_beat)
        rendered = re.sub(r"^\s*(CMD|ENTRYPOINT)\s+.*$", "", rendered, flags=re.MULTILINE).rstrip()
        return rendered + "\n" + addon
    rendered = _replace_cmd(rendered, web_cmd)
    rendered = _ensure_gunicorn_in_requirements(rendered)
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
        logger.info("entrypoint_detection", f"Node package detected (framework={info.get('framework')}).",
                    progress=12, details=info)
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
            "    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf",
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


class DockerfileGenerator:
    def render(self, *, platform: str, dockerfile_template: str, tar_stream,
               config: DeploymentConfig | None = None, logger=None) -> str:
        if not dockerfile_template:
            raise DeploymentValidationError("Dockerfile template is required.", stage="dockerfile_generation")
        check_requirements_txt(tar_stream, platform=platform)
        check_package_json(tar_stream, platform=platform)
        platform = (platform or "").lower().strip()
        if platform == "django":
            return _render_django(dockerfile_template, tar_stream, config, logger)
        if platform in ("flask", "python"):
            return _render_flask_or_python(platform, dockerfile_template, tar_stream, config, logger)
        if platform in ("nodejs", "nextjs", "react", "vuejs", "vue", "angular"):
            return _render_node_family(platform, dockerfile_template, tar_stream, config, logger)
        if platform == "php":
            return _render_php(dockerfile_template, tar_stream, config, logger)
        return _render_generic(platform, dockerfile_template, tar_stream, config, logger)
