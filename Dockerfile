FROM docker.arvancloud.ir/python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Debian 13 (Trixie) - IUT Mirror
RUN rm -f /etc/apt/sources.list.d/*.sources \
    && rm -f /etc/apt/sources.list.d/*.list \
    && printf '%s\n' \
        'deb http://repo.iut.ac.ir/debian/ trixie main' \
        'deb http://repo.iut.ac.ir/debian/ trixie-updates main' \
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

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "wsgi:application", "--bind", "0.0.0.0:8000"]