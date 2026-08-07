# Django PaaS Deployer

Self-hosted **Platform-as-a-Service** control plane built with Django.  
It turns uploaded application packages into running Docker containers, manages networks and exclusive volumes, and streams deployment progress in real time.

Pair it with the frontend:  
[react-paas-deployer](https://github.com/nima-salamat/react-paas-deployer)

---

## Purpose

The goal is to give developers a simple path from **source archive → live service**, without managing Docker by hand:

1. Create a **service** bound to a plan (CPU, RAM, storage) and a private network.
2. Upload a **deploy** (ZIP of the app) and select a platform (Django, Flask, FastAPI, Node, React, Vue, Angular, Vite, Go, PHP/Laravel, static, databases, …).
3. The platform **builds an image**, creates networks/volumes, starts a container, runs health checks, and publishes the app under a hostname on the deployment domain.
4. Users can **start / stop / rebuild**, inspect logs, attach storage, and roll back failed deploys.

It is designed for multi-tenant self-hosting: each user owns services, networks, and volumes under plan quotas.

---

## How it works

### High-level flow

```
Client (React)  →  Django API + Channels
                        │
                        ├─ Celery worker  →  Docker Engine
                        │                      ├─ build image
                        │                      ├─ create network / volume
                        │                      └─ run / replace container
                        │
                        └─ WebSocket groups  →  live deploy events & container logs
```

1. **API** accepts create/start/stop and stores deploy state in PostgreSQL.
2. **Celery** runs the orchestration pipeline asynchronously (`deployments` app).
3. **Orchestrator** uses docker-py to build images, prepare exclusive volumes, attach private networks, start containers, and health-check them.
4. **Platform plugins** detect stack and generate Dockerfile / start commands (Django, Node SPAs with nginx, databases via a dedicated DB deployer, etc.).
5. **Events** are written to a deployment-log database and broadcast over Channels so the UI can show progress live.
6. **Traefik** (in compose) routes public traffic to containers using labels / hostnames on `DEPLOYMENT_DOMAIN`.

### Core concepts

| Concept | Role |
|--------|------|
| **Service** | Long-lived app instance (name, plan, network, status, selected deploy). |
| **Deploy** | One version of an app (ZIP + config + platform). Can be selected and started. |
| **Plan** | Resource limits (CPU, RAM, storage) and platform type (app vs database). |
| **Private network** | User-scoped Docker network for service isolation. |
| **Volume** | Exclusive storage for one service; total size limited by plan storage quota. |

### Volume rules (summary)

- A volume belongs to **at most one** service (no sharing).
- **Attach / detach / delete** only when the service is stopped and its **container is gone**.
- **Name / size / path / mode** can be edited only if the Docker volume is **not** provisioned yet.
- Runtime cleanup endpoint can force-remove container and image so volumes can be changed safely.

### Supported platforms (plugin-based)

- **Python:** Django, Flask, FastAPI  
- **Node:** Express, React, Vue, Angular, Vite, Next.js  
- **Other:** Go, PHP/Laravel, static sites  
- **Databases:** MySQL, MariaDB, PostgreSQL, MongoDB, Redis, … (dedicated DB deploy path)

---

## Stack

- **Django 5** + Django REST Framework + SimpleJWT  
- **Celery** + Redis (queues, beat)  
- **Django Channels** + Redis (WebSockets)  
- **PostgreSQL** (main app DB + optional dedicated deployment-log DB)  
- **Docker** (docker-py against the host/engine socket)  
- **Gunicorn / Daphne** for HTTP and ASGI  
- **Docker Compose** for control-plane services (API, workers, Redis, Postgres, Traefik, …)

---

## Requirements

- Docker Engine and Docker Compose  
- Access to the Docker socket from the API/worker containers (or host)  
- Linux host recommended for production  

---

## Quick start

```bash
git clone https://github.com/nima-salamat/django-paas-deployer.git
cd django-paas-deployer

cp .env.example .env
# Edit SECRET_KEY, DB passwords, DOMAIN_NAME, DEPLOYMENT_DOMAIN, API_DOMAIN_NAME, RESEND_API_KEY

docker compose -f compose.yaml up -d --build
```

Typical services after compose is up:

- HTTP API / ASGI app  
- Celery worker + beat  
- Redis  
- Main PostgreSQL + deployment-log PostgreSQL  
- Reverse proxy (Traefik)

Run migrations if your entrypoint does not already:

```bash
docker compose exec <api-service> python manage.py migrate
docker compose exec <api-service> python manage.py createsuperuser
```

Point the React app’s `VITE_API_BASE` at your API domain.

---

## Configuration

See `.env.example` for the full list. Important variables:

| Variable | Meaning |
|----------|---------|
| `SECRET_KEY` | Django secret |
| `DEBUG` | `0` production, `1` development |
| `DB_*` | Main PostgreSQL |
| `DEPLOYMENT_LOG_DB_*` | Separate DB for deployment logs |
| `REDIS_URL` / `CHANNEL_REDIS_URL` | Celery and Channels |
| `DOMAIN_NAME` | Primary site domain |
| `DEPLOYMENT_DOMAIN` | Suffix for deployed apps (`app-….deploy.example.com`) |
| `API_DOMAIN_NAME` | Public API host |
| `RESEND_API_KEY` | Transactional email (OTP / recovery) |
| `DOCKER_MIRROR` | Optional registry mirror |

---

## Main API surface (overview)

- **Auth** (`auth_users`): login settings, OTP, JWT, invite links, recovery  
- **Services**: CRUD, start / stop / status, logs, purge container+image  
- **Networks**: private Docker networks per user  
- **Volumes**: exclusive volumes, files listing, archive download  
- **Deploys / deployments**: upload, select, orchestrate, live events  
- **Plans**: resource plans and platforms  

WebSockets (examples):

- Service container logs  
- Deployment event stream per deploy  

Exact paths follow the project’s URL includes (`/services/`, `/api/volumes/`, `/auth/`, …).

---

## Development notes

- Orchestration code lives under `deployments/` (Celery tasks, orchestrator, platform plugins, Docker managers).  
- Domain models for services, networks, and volumes live under `services/`.  
- Auth is isolated in `auth_users/`.  
- Prefer stopping a service and removing its container before mutating volumes in production.

---

## Related repository

Frontend dashboard (React + Vite + MUI):

**https://github.com/nima-salamat/react-paas-deployer**

---

## License

No license file is published in the repository yet. Add one if you intend to open the project for reuse.
