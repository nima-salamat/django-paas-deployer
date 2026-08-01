from django.db import models
from django.utils.translation import gettext_lazy as _


APPLICATIONS = [
    "php",
    "python",
    "django",
    "nextjs",
    "nodejs",
    "flask",
    "docker",
    "go",
    "statichtmlcss",
    "vuejs",
    "angular",
    "react",
    "dotnet",
]

DBS = [
    "mysql",
    "postgresql",
    "mariadb",
    "mongodb",
    "redis",
    "oracle",
]


PLATFORM_CHOICES = [
    ("php", "PHP"),
    ("python", "Python"),
    ("django", "Django"),
    ("nextjs", "Next.js"),
    ("nodejs", "Node.js"),
    ("flask", "Flask"),
    ("docker", "Docker"),
    ("go", "Go"),
    ("statichtmlcss", "Static HTML/CSS"),
    ("vuejs", "Vue.js"),
    ("angular", "Angular"),
    ("react", "React"),
    ("dotnet", ".NET"),
    ("mysql", "MySQL"),
    ("postgresql", "PostgreSQL"),
    ("mariadb", "MariaDB"),
    ("mongodb", "MongoDB"),
    ("redis", "Redis"),
    ("oracle", "Oracle"),
]


default_ports = {
    "php": 80,
    "python": None,
    "django": 8000,
    "nextjs": 3000,
    "nodejs": 3000,
    "flask": 5000,
    "docker": None,
    "go": None,
    "statichtmlcss": None,
    "vuejs": 8080,
    "angular": 4200,
    "react": 3000,
    "dotnet": 5000,

    "mysql": 3306,
    "postgresql": 5432,
    "mariadb": 3306,
    "mongodb": 27017,
    "redis": 6379,
    "oracle": 1521,
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
    READ = "read", _("Read-only")
    WRITE = "write", _("Write-only")
    READ_WRITE = "readwrite", _("Read & Write")


COLORS = [
    "#1abc9c",
    "#2ecc71",
    "#3498db",
    "#9b59b6",
    "#34495e",
    "#16a085",
    "#27ae60",
    "#2980b9",
    "#8e44ad",
    "#2c3e50",
    "#f1c40f",
    "#e67e22",
    "#e74c3c",
    "#ecf0f1",
    "#95a5a6",
    "#f39c12",
    "#d35400",
    "#c0392b",
    "#bdc3c7",
    "#7f8c8d",
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
    RUNNING = "running", _("running")      # container is confirmed up after deploy
    FAILED = "failed", _("failed")
    SUCCEEDED = "succeeded", _("succeeded")  # kept for backward compat; monitor maps → running
    STOPPING = "stopping", _("stopping")


MIRROR_DOCKER = "docker.arvancloud.ir"


class Config:

    php = """
FROM {MIRROR_DOCKER}/php:8.2-apache

ENV APACHE_DOCUMENT_ROOT=/var/www/html

COPY . /var/www/html/

RUN docker-php-ext-install mysqli pdo pdo_mysql opcache \\
    && a2enmod rewrite headers \\
    && sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf \\
    && echo "opcache.enable=1" >> /usr/local/etc/php/conf.d/opcache.ini

EXPOSE 80

CMD ["apache2-foreground"]
"""


    python = """
FROM {MIRROR_DOCKER}/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \\
    && pip install --no-cache-dir -r requirements.txt \\
    && pip install --no-cache-dir gunicorn uvicorn[standard]

COPY . /app

EXPOSE 8000

# Production server – overridden smartly by DockerfileGenerator when possible
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
"""


    django = """
FROM {MIRROR_DOCKER}/python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Debian 13 (Trixie) - IUT Mirror
RUN rm -f /etc/apt/sources.list.d/*.sources \\
    && rm -f /etc/apt/sources.list.d/*.list \\
    && printf '%s\\n' \\
        'deb http://repo.iut.ac.ir/debian/ trixie main' \\
        'deb http://repo.iut.ac.ir/debian/ trixie-updates main' \\
        > /etc/apt/sources.list \\
    && apt-get update \\
    && apt-get install -y --no-install-recommends \\
        build-essential \\
        libpq-dev \\
        python3-dev \\
        libjpeg-dev \\
        zlib1g-dev \\
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt /app/

RUN pip install --no-cache-dir --upgrade pip "setuptools<81" wheel \\
    && pip install --no-cache-dir -r requirements.txt \\
    && pip install --no-cache-dir gunicorn uvicorn[standard]

# Application
COPY . /app

EXPOSE 8000

# Production server – overridden by DockerfileGenerator (gunicorn / uvicorn + optional Celery)
CMD ["gunicorn", "{module}:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
"""


    nextjs = """
FROM {MIRROR_DOCKER}/node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build


FROM {MIRROR_DOCKER}/node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "start"]
"""


    nodejs = """
FROM {MIRROR_DOCKER}/node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev

COPY . .

EXPOSE 3000

CMD ["npm", "start"]
"""


    flask = """
FROM {MIRROR_DOCKER}/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \\
    && pip install --no-cache-dir -r requirements.txt \\
    && pip install --no-cache-dir gunicorn uvicorn[standard]

COPY . /app

EXPOSE 8000

# Production server – overridden smartly by DockerfileGenerator when possible
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
"""


    docker = """
FROM docker:dind

CMD ["dockerd"]
"""


    go = """
FROM {MIRROR_DOCKER}/golang:1.21-alpine

WORKDIR /app

COPY . .

RUN go build -o main .

EXPOSE 8080

CMD ["./main"]
"""


    static = """
FROM {MIRROR_DOCKER}/nginx:alpine

COPY . /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""


    vue = """
FROM {MIRROR_DOCKER}/node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build


FROM {MIRROR_DOCKER}/nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""


    angular = """
FROM {MIRROR_DOCKER}/node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build


FROM {MIRROR_DOCKER}/nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""


    react = """
FROM {MIRROR_DOCKER}/node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build


FROM {MIRROR_DOCKER}/nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""


    dotnet = """
FROM mcr.microsoft.com/dotnet/aspnet:6.0 AS base

WORKDIR /app

EXPOSE 80


FROM mcr.microsoft.com/dotnet/sdk:6.0 AS build

WORKDIR /src

COPY . .

RUN dotnet publish -c Release -o /app/publish


FROM base AS final

WORKDIR /app

COPY --from=build /app/publish .

ENTRYPOINT ["dotnet", "YourAppName.dll"]
"""


MAX_DEPLOY_TIME_MINUTE = 10
