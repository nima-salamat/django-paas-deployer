ARG DOCKERFILE_DOCKER_MIRROR=docker.io
ARG DOCKERFILE_PYTHON_MIRROR=https://pypi.org/simple
ARG DOCKERFILE_LINUX_MIRROR=http://deb.debian.org/debian

FROM ${DOCKERFILE_DOCKER_MIRROR}/python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


RUN rm -f /etc/apt/sources.list.d/*.sources \
    && rm -f /etc/apt/sources.list.d/*.list \
    && printf '%s\n' \
        "deb ${DOCKERFILE_LINUX_MIRROR} trixie main" \
        "deb ${DOCKERFILE_LINUX_MIRROR} trixie-updates main" \
        > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        python3-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install \
        -i "${DOCKERFILE_PYTHON_MIRROR}" \
        --upgrade pip \
    && pip install \
        -i "${DOCKERFILE_PYTHON_MIRROR}" \
        --no-cache-dir \
        -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "asgi:application", "--host", "0.0.0.0", "--port", "8000"]