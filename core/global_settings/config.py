from django.db import models
from django.utils.translation import gettext_lazy as _


APPLICATIONS = [
    "php", "laravel", "python", "django", "nextjs", "nodejs", "flask", "docker", "go",
    "statichtmlcss", "vuejs", "angular", "react", "dotnet",
]

DBS = ["mysql", "postgresql", "mariadb", "mongodb", "redis", "oracle"]

PLATFORM_CHOICES = [
    ("php", "PHP"), ("laravel", "Laravel"), ("python", "Python"), ("django", "Django"),
    ("nextjs", "Next.js"), ("nodejs", "Node.js"), ("flask", "Flask"),
    ("docker", "Docker"), ("go", "Go"), ("statichtmlcss", "Static HTML/CSS"),
    ("vuejs", "Vue.js"), ("angular", "Angular"), ("react", "React"),
    ("dotnet", ".NET"), ("mysql", "MySQL"), ("postgresql", "PostgreSQL"),
    ("mariadb", "MariaDB"), ("mongodb", "MongoDB"), ("redis", "Redis"),
    ("oracle", "Oracle"),
]

# Fallback when DB settings are empty
default_ports = {
    "php": 80, "laravel": 80, "python": None, "django": 8000, "nextjs": 3000, "nodejs": 3000,
    "flask": 5000, "docker": None, "go": None, "statichtmlcss": 80,
    "vuejs": 80, "angular": 80, "react": 80, "dotnet": 5000,
    "mysql": 3306, "postgresql": 5432, "mariadb": 3306, "mongodb": 27017,
    "redis": 6379, "oracle": 1521,
}

DEFAULT_MAX_APPS = 2


class PlanTypeChoices(models.TextChoices):
    DB = "DB", _("Database")
    APP = "APP", _("Application")
    READY = "READY", _("Ready-made")


class StorageTypeChoices(models.TextChoices):
    SSD = "SSD", _("SSD")
    HDD = "HDD", _("HDD")


class NameChoices(models.TextChoices):
    BRONZE = "Bronze", _("Bronze")
    SILVER = "Silver", _("Silver")
    GOLD = "Gold", _("Gold")
    DIAMOND = "Diamond", _("Diamond")


class VOLUME_MODE_CHOICES(models.TextChoices):
    READ = "r", _("Read-only")
    WRITE = "w", _("Write-only")
    READ_WRITE = "rw", _("Read & Write")


COLORS = [
    "#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#34495e", "#16a085",
    "#27ae60", "#2980b9", "#8e44ad", "#2c3e50", "#f1c40f", "#e67e22",
    "#e74c3c", "#ecf0f1", "#95a5a6", "#f39c12", "#d35400", "#c0392b",
    "#bdc3c7", "#7f8c8d",
]
COLOR_CHOICES = [(i, j) for i, j in enumerate(COLORS, 0)]


class PaymentChoices(models.TextChoices):
    PAYED = "PAYED"
    NOT_PAYED = "NOT_PAYED"
    CANCELED = "CANCELED"


class SERVICE_STATUS_CHOICES(models.TextChoices):
    STOPPED = "stopped", _("stopped")
    QUEUED = "queued", _("queued")
    DEPLOYING = "deploying", _("deploying")
    RUNNING = "running", _("running")
    FAILED = "failed", _("failed")
    SUCCEEDED = "succeeded", _("succeeded")
    STOPPING = "stopping", _("stopping")


# Code-level fallbacks (DB SystemSetting overrides these at runtime)
MIRROR_DOCKER = "docker.arvancloud.ir"
MIRROR_PYTHON = "https://mirror-pypi.runflare.com/simple"

DEFAULT_RUNTIME_VERSIONS = {
    "python_version": "3.11",
    "django_python_version": "3.10",
    "node_version": "20",
    "php_version": "8.2",
    "go_version": "1.21",
    "dotnet_version": "6.0",
    "nginx_version": "alpine",
}

DEFAULT_WORKER_COUNT = 1
DEFAULT_SPA_BUILD_DIR = "dist"
DEFAULT_EXPOSE_PORT = 80
MAX_DEPLOY_TIME_MINUTE = 10


class Config:
    """Dockerfile templates — placeholders filled by DeploymentHelper."""

    php = """
FROM {MIRROR_DOCKER}/php:{php_version}-apache

ENV APACHE_DOCUMENT_ROOT=/var/www/html \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_MEMORY_LIMIT=-1

WORKDIR /var/www/html

RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev libicu-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j$(nproc) mysqli pdo pdo_mysql opcache zip gd intl bcmath \
    && a2enmod rewrite headers \
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \
    && (grep -q '^ServerName ' /etc/apache2/apache2.conf || echo 'ServerName localhost' >> /etc/apache2/apache2.conf) \
    && echo "opcache.enable=1" >> /usr/local/etc/php/conf.d/opcache.ini \
    && rm -rf /var/lib/apt/lists/*

COPY --from={MIRROR_DOCKER}/composer:2 /usr/bin/composer /usr/bin/composer

COPY . /var/www/html/

RUN if [ -f composer.json ]; then \
      composer install --no-dev --prefer-dist --no-interaction --no-progress --optimize-autoloader --no-scripts \
      && test -f vendor/autoload.php \
      && echo "composer install OK"; \
    fi \
    && mkdir -p storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache \
    && chown -R www-data:www-data /var/www/html \
    && chmod -R ug+rwx storage bootstrap/cache 2>/dev/null || true

EXPOSE {port}
CMD ["apache2-foreground"]
"""

    # Dedicated Laravel entry — same base image, deployer forces public/ + migrate
    laravel = php

    python = """
FROM {MIRROR_DOCKER}/python:{python_version}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_DEFAULT_TIMEOUT={PIP_DEFAULT_TIMEOUT} \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /app/
RUN pip install -i {MIRROR_PYTHON} --trusted-host $(echo {MIRROR_PYTHON} | sed -E 's|https?://([^/]+).*|\\1|') \\
        --no-cache-dir --upgrade pip \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir -r requirements.txt \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir gunicorn uvicorn[standard]
COPY . /app
EXPOSE {port}
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "60"]
"""

    django = """
FROM {MIRROR_DOCKER}/python:{django_python_version}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_DEFAULT_TIMEOUT={PIP_DEFAULT_TIMEOUT} \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN rm -f /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list \\
    && printf '%s\\n' \\
        'deb {MIRROR_APT} trixie main' \\
        'deb {MIRROR_APT} trixie-updates main' \\
        > /etc/apt/sources.list \\
    && apt-get update \\
    && apt-get install -y --no-install-recommends \\
        build-essential libpq-dev python3-dev libjpeg-dev zlib1g-dev \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install -i {MIRROR_PYTHON} --no-cache-dir --upgrade pip "setuptools<81" wheel \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir -r requirements.txt \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir gunicorn uvicorn[standard]
COPY . /app
EXPOSE {port}
CMD ["gunicorn", "{module}:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "60"]
"""

    flask = """
FROM {MIRROR_DOCKER}/python:{python_version}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    FLASK_ENV=production \\
    PIP_DEFAULT_TIMEOUT={PIP_DEFAULT_TIMEOUT} \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /app/
RUN pip install -i {MIRROR_PYTHON} --no-cache-dir --upgrade pip \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir -r requirements.txt \\
    && pip install -i {MIRROR_PYTHON} --no-cache-dir gunicorn uvicorn[standard]
COPY . /app
EXPOSE {port}
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "60"]
"""

    nextjs = """
FROM {MIRROR_DOCKER}/node:{node_version}-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build
FROM {MIRROR_DOCKER}/node:{node_version}-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
EXPOSE {port}
CMD ["npm", "start"]
"""

    nodejs = """
FROM {MIRROR_DOCKER}/node:{node_version}-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev
COPY . .
EXPOSE {port}
CMD ["npm", "start"]
"""

    docker = """
FROM docker:dind
CMD ["dockerd"]
"""

    go = """
FROM {MIRROR_DOCKER}/golang:{go_version}-alpine
WORKDIR /app
COPY . .
RUN go build -o main .
EXPOSE {port}
CMD ["./main"]
"""

    static = """
FROM {MIRROR_DOCKER}/nginx:{nginx_version}
COPY . /usr/share/nginx/html
EXPOSE {port}
CMD ["nginx", "-g", "daemon off;"]
"""

    vue = """
FROM {MIRROR_DOCKER}/node:{node_version}-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build
FROM {MIRROR_DOCKER}/nginx:{nginx_version}
COPY --from=builder /app/{build_dir} /usr/share/nginx/html
EXPOSE {port}
CMD ["nginx", "-g", "daemon off;"]
"""

    angular = vue  # same multi-stage shape; build_dir differs per project
    react = vue

    # Fix angular/react properly
    angular = """
FROM {MIRROR_DOCKER}/node:{node_version}-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build
FROM {MIRROR_DOCKER}/nginx:{nginx_version}
COPY --from=builder /app/{build_dir} /usr/share/nginx/html
EXPOSE {port}
CMD ["nginx", "-g", "daemon off;"]
"""

    react = """
FROM {MIRROR_DOCKER}/node:{node_version}-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build
FROM {MIRROR_DOCKER}/nginx:{nginx_version}
COPY --from=builder /app/{build_dir} /usr/share/nginx/html
EXPOSE {port}
CMD ["nginx", "-g", "daemon off;"]
"""

    dotnet = """
FROM mcr.microsoft.com/dotnet/aspnet:{dotnet_version} AS base
WORKDIR /app
EXPOSE {port}
FROM mcr.microsoft.com/dotnet/sdk:{dotnet_version} AS build
WORKDIR /src
COPY . .
RUN dotnet publish -c Release -o /app/publish
FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "YourAppName.dll"]
"""

    vuejs = vue
    statichtmlcss = static
