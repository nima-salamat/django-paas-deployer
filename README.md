# Django PaaS Deployer

PassDeployer is a self-hosted, multi-tenant Django PaaS control plane. It builds and deploys application workloads, manages service configuration and revisions, provisions databases, streams logs, and exposes an operator control plane through Wagtail.

## Runtime model

```text
Service
  -> ServiceRevision
  -> ServiceRuntimeGraph
  -> Docker image / external image
  -> Swarm Service (one per enabled process)
  -> Swarm Task (replica = 1)
```

Docker Compose remains the installation/runtime-specification format for the PassDeployer control plane. Tenant applications are not launched with `docker compose up`.

## Repository layout

```text
.
├── documentation/     Project and subsystem documentation
├── src/                All Django/Python application source and source assets
├── scripts/            Operator/developer helper scripts
├── .github/            CI workflows
├── compose.yaml        Control-plane orchestration
├── Dockerfile          Control-plane image
├── entrypoint.sh       Container bootstrap
├── manage.py           Django management entrypoint
├── requirements.txt    Python dependencies
└── pytest.ini          Test configuration
```

The `src/` tree contains the Django project package, all domain apps, deployment runtime code, static assets and global templates. The repository root is intentionally reserved for operational/tooling entrypoints.

## Documentation

The canonical documentation is under [documentation/](documentation/README.md). It explains architecture, installation, runtime behavior, reconciliation, domain models, databases/storage, catalog ingestion, observability, Wagtail administration, component boundaries, testing and security.

The `src/docs/` directory is a Django application for product document/public-asset behavior. It is not the project documentation directory.

## Main ownership boundaries

- `src/services`: user-owned Service configuration, processes, revisions, secrets, endpoints, networks, volumes and database bindings.
- `src/deploy`: deployment operation/history and lifecycle metadata.
- `src/deployments`: build/execution engine, Swarm runtime, readiness, reconciliation and cleanup.
- `src/app_catalog`: declarative catalog definitions, Compose normalization and multi-service installation planning.
- `src/plans`: resource/execution policy.
- `src/logs`: runtime/deployment log ingestion and retention.
- `src/core`: cross-cutting platform facilities.
- `src/users` + `src/auth_users`: identity, permissions and authentication.
- `src/cms`: Wagtail integration.
- `src/messenger`: real-time messaging and calls.
- `src/tickets`: support workflows.
- `src/custom_emails`: transactional email.
- `src/docs`: product document/asset API.

## Runtime invariants

A Service is the durable user-owned workload. A ServiceRevision is immutable executable state. A Deploy records an execution operation and provenance; it is not the runtime owner.

Each enabled ServiceProcess becomes one actual Swarm Service and the platform currently permits exactly one replica. Stop is represented by desired state plus scaling managed Swarm Services to zero; start/redeploy converges back to one replica.

Observed runtime comes from Docker Swarm Service/Task state. The database stores desired state and provenance.

## Resource and security policy

Tenant input does not control Docker host privileges, arbitrary host mounts, Docker socket access, privileged mode, device passthrough, arbitrary networks, or unrestricted resource limits. Build and runtime resource policy is server-owned.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

For Swarm setup, registry, networking and production topology, read [documentation/installation.md](documentation/installation.md).

## Related project

React dashboard: https://github.com/nima-salamat/react-paas-deployer
