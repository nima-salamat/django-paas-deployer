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
