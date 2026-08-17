import io
import tarfile

from deployments.core.entrypoints import check_requirements_txt


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


def test_python_pyproject_is_accepted():
    tar = make_tar({"pyproject.toml": "[project]\nname='demo'\ndependencies=[]\n"})
    check_requirements_txt(tar, platform="python")


def test_python_pipfile_is_accepted():
    tar = make_tar({"Pipfile": "[packages]\n"})
    check_requirements_txt(tar, platform="python")


def test_pnpm_lockfile_is_detected_and_prepared():
    from deployments.core.dockerfile import _detect_node_package_manager_from_tar, _prepare_node_package_manager
    tar = make_tar({"package.json": '{"packageManager":"pnpm@9.0.0"}', "pnpm-lock.yaml": "lockfileVersion: '9.0'\n"})
    assert _detect_node_package_manager_from_tar(tar) == "pnpm"
    df = "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\n"
    out = _prepare_node_package_manager(df, "pnpm")
    assert "corepack enable" in out
    assert "COPY pnpm-lock.yaml ./" in out


def test_yarn_lockfile_is_prepared():
    from deployments.core.dockerfile import _prepare_node_package_manager
    df = "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\n"
    out = _prepare_node_package_manager(df, "yarn")
    assert "corepack enable" in out
    assert "COPY yarn.lock ./" in out


def test_bun_lockfile_is_prepared():
    from deployments.core.dockerfile import _prepare_node_package_manager
    tar = make_tar({"package.json": '{"packageManager":"bun@1.0.0"}', "bun.lockb": ""})
    from deployments.core.dockerfile import _detect_node_package_manager_from_tar
    assert _detect_node_package_manager_from_tar(tar) == "bun"
    df = "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\n"
    out = _prepare_node_package_manager(df, "bun")
    assert "npm install -g bun" in out
    assert "COPY bun.lockb ./" in out


def test_php_wrapped_archive_uses_app_root_for_composer():
    from deployments.core.dockerfile import _detect_php_document_root, _detect_php_project, _render_php
    import base64

    tar = make_tar({
        "Acme/composer.json": '{"require":{"php":"^8.2","ext-intl":"*","ext-zip":"*"}}',
        "Acme/public/index.php": "<?php",
        "Acme/artisan": "#!/usr/bin/env php\n",
    })
    assert _detect_php_document_root(tar) == "Acme/public"
    info = _detect_php_project(tar)
    assert info["has_composer"] is True
    assert set(info["composer"]["extensions"]) == {"intl", "zip"}

    class ConfigStub:
        entry_point = None
        environment = {}
        platform = "laravel"
        document_root = None

    dockerfile = (
        "FROM registry.example.test/php:8.2-apache\n"
        "COPY . /var/www/html/\n"
        "RUN docker-php-ext-install mysqli pdo pdo_mysql opcache\n"
    )
    out = _render_php(dockerfile, tar, ConfigStub(), None)
    assert "COPY --from=registry.example.test/composer:2" in out
    assert "RUN cd /var/www/html/Acme" in out
    assert "docker-php-ext-install intl zip" in out
    assert base64.b64encode(b"/var/www/html/Acme/public").decode() in out
