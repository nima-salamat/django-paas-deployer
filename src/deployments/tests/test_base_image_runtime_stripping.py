from deployments.core.dockerfile import _strip_base_owned_php_runtime


def test_base_image_strips_legacy_php_runtime_install():
    dockerfile = """FROM paas-base/php-apache:8.4-r1
WORKDIR /var/www/html
RUN apt-get update && apt-get install -y --no-install-recommends         git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev         libicu-dev libonig-dev libxml2-dev curl ca-certificates     && docker-php-ext-configure gd --with-freetype --with-jpeg     && docker-php-ext-install -j$(nproc)         mysqli pdo pdo_mysql opcache zip gd intl bcmath mbstring exif pcntl     && a2enmod rewrite headers mime dir expires alias     && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf     && echo \"opcache.enable=1\" >> /usr/local/etc/php/conf.d/opcache-laravel.ini     && rm -rf /var/lib/apt/lists/*
COPY . /var/www/html/
"""
    out = _strip_base_owned_php_runtime(dockerfile)
    assert "apt-get update" not in out
    assert "docker-php-ext-install" not in out
    assert "COPY . /var/www/html/" in out
    assert out.startswith("FROM paas-base/php-apache:8.4-r1")


def test_multiline_php_runtime_fallback_is_stripped():
    from deployments.core.dockerfile import _strip_base_owned_php_runtime
    dockerfile = """\nFROM paas-base/php-apache:8.4-r1\nRUN docker-php-ext-install mysqli pdo pdo_mysql \\n    && a2enmod rewrite headers mime\
RUN echo \"app\" > /tmp/app\n"""
    out = _strip_base_owned_php_runtime(dockerfile)
    assert "docker-php-ext-install" not in out
    assert "a2enmod" not in out
    assert "RUN echo" in out


def test_tenant_apt_package_is_preserved_with_custom_php_extension():
    dockerfile = """FROM paas-base/php-apache:8.4-r1
RUN apt-get update && apt-get install -y --no-install-recommends git unzip libzip-dev tenant-extra-package \
    && docker-php-ext-install sockets
RUN echo "keep"
"""
    out = _strip_base_owned_php_runtime(dockerfile)
    assert "tenant-extra-package" in out
    assert "docker-php-ext-install sockets" in out


def test_multiple_php_stages_only_replace_apache_runtime_stage():
    from types import SimpleNamespace
    from deployments.core.dockerfile import _apply_resolved_base_images

    dockerfile = """FROM php:8.4-apache AS runtime
RUN echo runtime
FROM php:8.4-cli AS builder
RUN apt-get update && apt-get install -y --no-install-recommends tenant-package \
    && docker-php-ext-install sockets
"""
    config = SimpleNamespace(
        base_images={"base_image": "paas-base/php-apache:8.4-r1"},
        platform="php",
    )
    out = _apply_resolved_base_images(dockerfile, config)
    assert "FROM paas-base/php-apache:8.4-r1 AS runtime" in out
    assert "FROM php:8.4-cli AS builder" in out
    assert "tenant-package" in out
    assert "docker-php-ext-install sockets" in out


def test_php_laravel_runtime_uses_cached_base_without_duplicate_base_runtime_setup():
    from types import SimpleNamespace
    from deployments.core.dockerfile import _apply_resolved_base_images

    dockerfile = """FROM php:8.4-apache
RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev \
        libicu-dev libonig-dev libxml2-dev \
    && docker-php-ext-install -j$(nproc) mysqli pdo pdo_mysql opcache zip gd intl bcmath mbstring exif pcntl \
    && a2enmod rewrite headers \
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
    && echo "opcache.enable=1" >> /usr/local/etc/php/conf.d/opcache-laravel.ini \
    && rm -rf /var/lib/apt/lists/*
COPY . /var/www/html/
"""
    config = SimpleNamespace(
        base_images={"base_image": "paas-base/php-apache:8.4-r1"},
        platform="laravel",
    )
    out = _apply_resolved_base_images(dockerfile, config)
    assert out.count("FROM paas-base/php-apache:8.4-r1") == 1
    assert "docker-php-ext-install" not in out
    assert "COPY . /var/www/html/" in out


def test_custom_php_extension_injected_after_base_substitution_is_not_stripped():
    from types import SimpleNamespace
    from deployments.core.dockerfile import _apply_resolved_base_images

    dockerfile = """FROM php:8.4-apache
COPY . /var/www/html/
RUN apt-get update && apt-get install -y --no-install-recommends libssl-dev \
    && docker-php-ext-install redis
"""
    config = SimpleNamespace(
        base_images={"base_image": "paas-base/php-apache:8.4-r1"},
        platform="php",
    )
    out = _apply_resolved_base_images(dockerfile, config)
    assert "libssl-dev" in out
    assert "docker-php-ext-install redis" in out
