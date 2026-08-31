import io
import tarfile
import types
import sys


def make_tar(files):
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    bio.seek(0)
    return bio


def load_dockerfile_module():
    mod = types.ModuleType("core.global_settings.config")
    mod.MIRROR_DOCKER = "mirror.test"
    sys.modules["core.global_settings.config"] = mod
    pkg = types.ModuleType("core.global_settings")
    pkg.__path__ = []
    sys.modules["core.global_settings"] = pkg
    from deployments.core import dockerfile
    return dockerfile


def test_react_template_tokens_are_resolved():
    d = load_dockerfile_module()
    template = '''FROM mirror.test/node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
__DEPLOY_INSTALL_COMMAND__
COPY . .
__DEPLOY_BUILD_COMMAND__
FROM mirror.test/nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
'''
    class Config:
        entry_point = None
        environment = {}
        package_manager = "npm"
        install_command = "npm ci"
        build_command = "npm run build"
        build_dir = "dist"
        port = 80
    out = d._render_node_family("react", template, make_tar({
        "package.json": '{"scripts":{"build":"vite build"},"dependencies":{"react":"19"},"devDependencies":{"vite":"7"}}',
        "package-lock.json": "{}",
    }), Config(), None)
    assert "__DEPLOY_" not in out
    assert "RUN npm ci" in out
    assert "RUN npm run build" in out


def test_laravel_frontend_detection_works_with_bytesio_tar():
    d = load_dockerfile_module()
    detected = d._detect_laravel_frontend(make_tar({
        "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
        "artisan": "<?php",
        "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
        "package-lock.json": "{}",
    }))
    assert detected["has_package_json"] is True
    assert detected["kind"] == "vite"
    assert detected["package_manager"] == "npm"


def test_laravel_frontend_does_not_reuse_composer_install_command():
    d = load_dockerfile_module()
    class Config:
        environment = {}
        frontend = {}
        package_manager = "npm"
        install_command = "composer install --no-dev --optimize-autoloader"
        build_command = "npm run build"
        runtime_version = None
        build_options = {}
    out = d._inject_laravel_frontend_build(
        "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
        tar_stream=make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
            "package-lock.json": "{}",
        }),
        config=Config(), logger=None,
    )
    frontend_block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
    assert "npm ci" in frontend_block
    assert "npm run build" in frontend_block
    assert "composer install --no-dev" not in frontend_block


def test_laravel_frontend_detects_pnpm():
    d = load_dockerfile_module()
    detected = d._detect_laravel_frontend(make_tar({
        "package.json": '{"packageManager":"pnpm@10.0.0","scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
        "pnpm-lock.yaml": "lockfileVersion: '9'\n",
    }))
    assert detected["has_package_json"] is True
    assert detected["package_manager"] == "pnpm"
