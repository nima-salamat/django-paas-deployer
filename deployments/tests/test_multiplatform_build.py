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
    # POST-FLATTEN: the image build strips the single top-level 'Acme'
    # wrapper, so the DocumentRoot is relative to /var/www/html.
    assert _detect_php_document_root(tar) == "public"
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
    import re as _re

    assert _re.search(r"COPY --from=\S+/composer:2 /usr/bin/composer", out)
    # Composer runs in the app root — post-flatten (no 'Acme' prefix).
    assert "RUN cd /var/www/html \\" in out
    assert "/var/www/html/Acme" not in out
    assert "docker-php-ext-install intl zip" in out
    assert "ENV APACHE_DOCUMENT_ROOT=/var/www/html/public" in out
    # The base64-encoded VirtualHost serves the post-flatten document root.
    conf_blob = next(
        line.split("'", 2)[1]
        for line in out.splitlines()
        if line.startswith("RUN echo '")
    )
    assert f"DocumentRoot /var/www/html/public" in base64.b64decode(conf_blob).decode()
