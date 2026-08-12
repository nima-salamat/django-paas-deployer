ARG DOCKERFILE_DOCKER_MIRROR=docker.io
ARG DOCKERFILE_PYTHON_MIRROR=https://pypi.org/simple
ARG DOCKERFILE_PYTHON_VERSION=3.10-slim-trixie
FROM ${DOCKERFILE_DOCKER_MIRROR}/python:${DOCKERFILE_PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG DOCKERFILE_LINUX_MIRROR=http://deb.debian.org/debian
ARG CODENAME=trixie
# Configure Debian Linux mirror
RUN set -eux; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME}"; \
    rm -f /etc/apt/sources.list.d/*.sources; \
    rm -f /etc/apt/sources.list.d/*.list; \
    printf '%s\n' \
        "deb ${DOCKERFILE_LINUX_MIRROR} ${CODENAME} main" \
        "deb ${DOCKERFILE_LINUX_MIRROR} ${CODENAME}-updates main" \
        > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        python3-dev \
        libjpeg-dev \
        zlib1g-dev; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

ARG DOCKERFILE_PYTHON_MIRROR

RUN pip install \
        --index-url "${DOCKERFILE_PYTHON_MIRROR:-https://pypi.org/simple}" \
        --upgrade pip \
    && pip install \
        --index-url "${DOCKERFILE_PYTHON_MIRROR:-https://pypi.org/simple}" \
        --no-cache-dir \
        -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]