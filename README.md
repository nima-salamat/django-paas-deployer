# Django PaaS Deployer

A self-hosted multi-tenant PaaS control plane that turns application archives into isolated Docker workloads. It supports application builds, Laravel/React-style frontend builds, database deployments, live deployment logs, Docker event reconciliation, rollback, and plan-based resource governance.

## Architecture

```text
Client / React Dashboard
        │
        ├── HTTPS API ───────────────┐
        │                            │
        └── WebSocket                ▼
                              Django / Channels
                                   │
                         Celery deployment queues
                                   │
                       ┌───────────┴───────────┐
                       ▼                       ▼
                 deployment-worker       deployment events
                       │                       │
                       └────── Docker Engine ─┘

Celery Beat / reconciliation = repair mechanism, NOT runtime truth
```

The Docker daemon is the runtime source of truth. The event consumer listens to Docker Engine events and updates deployment/container state immediately. WebSockets are delivery only; they are not the authoritative state store. Periodic reconciliation remains enabled to repair missed events, daemon restarts, Redis outages, or external Docker changes.

## Resource governance

**Tenants do not control CPU, RAM, swap, PIDs, worker counts, Docker host configuration, or build concurrency.**

Runtime resources come from the selected `Service -> Plan`. Build resources are server-owned. The current default is a static operator-defined build budget, but the system also supports a future/optional `plan` build mode without changing the tenant API:

- `build.resource_mode=static`: every build uses the operator build budget.
- `build.resource_mode=plan`: the selected Plan's CPU/RAM becomes the requested build budget, still capped by operator hard ceilings.

This policy can therefore be changed later centrally without trusting values sent in `Deploy.config`. Build concurrency is also globally bounded across horizontally scaled deployment workers with a Redis-backed distributed semaphore.

## Tenant configuration

`Deploy.config` is intentionally limited to application behavior. Examples of supported controls include platform/framework selection where permitted by the selected Plan, runtime version, package manager, frontend install/build command, build output directory, health-check/runtime metadata, environment variables, application port, and application start command.

The following are never trusted from tenant input: `cpu`, `memory`, `memory_mb`, `memory_swap_mb`, `pids_limit`, `worker_count`, `privileged`, `cap_add`, `devices`, Docker host config, arbitrary host mounts, arbitrary Docker networks, arbitrary build network mode, and similar host-isolation controls.

### Laravel + React/Vite

Laravel projects can include a Node frontend build. The deploy pipeline can detect `package.json`/lockfiles and execute a frontend build before the PHP runtime image is finalized. Dev dependencies are available during the build because Vite, TypeScript, React and related tooling commonly live in `devDependencies`. A failed frontend build is a deployment failure; it is never converted into success with `|| true`.

Supported package-manager families include npm, pnpm, yarn, and bun where the project/platform supports them. Custom install/build commands are validated before they are placed into generated Dockerfiles.

## Cancellation semantics

`force_cancel` accepts a `deploy_id` (preferred) or the legacy `service_id`. It is idempotent and transactionally marks the target deployment as `cancelled` before attempting worker termination. Celery revoke/terminate is best-effort; Docker events then provide immediate runtime state changes.

Most importantly, cancellation is **deployment-scoped**. If a previous version of the service is still serving traffic while a new version is being built, cancelling the new build does not blindly remove the old live container or its image. Only containers labeled with the target deployment ID and the target deployment image are eligible for cleanup.

## Docker event consumer

Run: `python manage.py consume_docker_events`

The consumer tracks managed container labels, especially:

- `managed-by=django-paas-deployer`
- `deployment.id=<Deploy primary key>`
- `service.id=<Service primary key>`

Relevant Docker lifecycle events such as `create`, `start`, `die`, `stop`, `kill`, `destroy`, health-status changes, and OOM signals can be mapped to deployment state/logging. The event consumer should run as a dedicated service in production.

## Queue topology

Long Docker builds run on the dedicated `deployments` / `operations` queues, isolated from generic application Celery work. Multiple `deployment-worker` replicas may consume the same queue. Build concurrency is separately bounded by the Redis build semaphore.

## Security boundaries

The deployer is designed for untrusted source archives. Important protections include archive traversal checks, tar extraction safety, symlink rejection, bounded upload/extraction sizes, validated Docker identifiers, sanitized build/start command overrides, server-owned Docker resource policy, restricted bind-mount prefixes, no tenant-controlled privileged Docker options, and deployment-scoped cleanup.

The Docker socket is a high-trust boundary. Production deployments should therefore keep the control-plane containers isolated, restrict who can reach the management API, use strong secrets, and avoid exposing the Docker socket to containers that do not require it.

## Main components

- Django 5 + Django REST Framework + SimpleJWT
- Django Channels + Redis
- Celery + Redis
- PostgreSQL for control-plane state
- Optional separate PostgreSQL deployment-log store
- Docker Engine / docker-py
- Traefik for deployment routing
- Docker event consumer for runtime reconciliation

## Configuration

Important server-owned build settings are stored through the system settings service and can be centrally changed by operators:

| Setting | Default | Purpose |
|---|---:|---|
| `build.resource_mode` | `static` | Build budget source: static operator budget or selected Plan |
| `build.max_cpu` | `1.0` | Operator hard CPU ceiling for builds |
| `build.max_ram_mb` | `1024` | Operator hard RAM ceiling for builds |
| `deploy.build_pids_limit` | `2048` | PID limit for untrusted build workloads |
| `build.parallelism` | `1` | Maximum concurrent Docker builds across workers |
| `build.max_wait_minute` | `5` | Maximum wait for a build semaphore slot |
| `deploy.mb_per_worker` | `256` | Server-side RAM budget per derived runtime worker |
| `deploy.runtime_worker_cap` | `8` | Hard runtime worker cap |
| `deploy.max_time_minute` | `10` | Reconciliation timeout for stuck deploys |

Environment variables are available for bootstrapping/fallback. The canonical operator controls are the system settings with the keys above; tenants never receive an API parameter that can override these values.

## Quick start

```bash
cp .env.example .env
docker compose -f compose.yaml up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Production should run the API, generic Celery workers, dedicated deployment workers, the Docker event consumer, Redis, PostgreSQL, and Traefik as separate services.

## Operational checks

Before production rollout, verify:

1. `deployment-events` stays connected to the Docker daemon and reconnects after daemon restart.
2. Build concurrency remains bounded when multiple `deployment-worker` replicas are running.
3. A cancelled build transitions to `cancelled` immediately without waiting for Beat.
4. Cancelling a new deployment does not remove the previous healthy deployment.
5. A failed build cannot become `succeeded` due to a late worker result.
6. Runtime CPU/RAM values match the Service Plan, never the request body.
7. `build.resource_mode=plan` still respects operator hard ceilings.
8. No tenant can mount `/var/run/docker.sock`, `/etc`, `/root`, or arbitrary host paths.

## Related frontend

React dashboard: https://github.com/nima-salamat/react-paas-deployer


## Deployment resource policy

Deployment resource allocation is server-authoritative. Tenants cannot select CPU, RAM, PIDs, worker counts, Docker host configuration, or build limits through `Deploy.config`.

### Build resources

Build resources are resolved by `deployments.common.resource_policy.build_limits(plan)`:

- `build.resource_mode=static`: use operator-defined fixed build limits.
- `build.resource_mode=plan`: derive the requested build budget from the selected Service Plan and clamp it to operator hard ceilings.

This makes the policy easy to change later without changing the tenant API or deployment schema. The build policy is passed to the executor as `DeploymentConfig.build_resource_policy` and is never read from user config.

### Runtime resources

Runtime CPU/RAM are taken only from the selected Service Plan. Worker count is derived server-side from the same plan and operator tuning parameters.

### Compatibility

`DeploymentConfig.build_resource_policy` is part of the executor contract. Older call sites that only provide `build_options` remain valid because the field has a safe empty default.

### Force cancel

Force-cancel is deployment-scoped. It updates the target deployment state first, revokes the Celery task when possible, and removes only artifacts belonging to the cancelled deployment. A running previous/production deployment must not be removed merely because a newer build was cancelled.

### Lifecycle source of truth

Docker Events are used for runtime lifecycle reconciliation and live WebSocket updates. Scheduler/beat is retained only for periodic reconciliation and recovery; it is not required for normal state propagation.
