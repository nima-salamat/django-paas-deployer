# Development

## Source layout

All application source and source assets live under `src/`.

```text
src/
├── config/          Django settings, URLs, ASGI/WSGI, Celery
├── services/        Service domain
├── deploy/          deployment operations
├── deployments/     execution/runtime engine
├── app_catalog/     catalog ingestion
├── plans/           resource policy
├── logs/            observability
├── users/
├── auth_users/
├── cms/
├── core/
├── docs/             product Django app
├── messenger/
├── tickets/
├── custom_emails/
├── static/
└── templates/
```

Root files are operational entrypoints or tooling.

## Django entrypoints

- `python manage.py ...`
- `config.settings`
- `config.urls`
- `config.asgi:application`
- `config.wsgi:application`
- `config.celery`

`manage.py`, Docker and pytest all make `src/` importable.

## Extension boundary

Keep user intent in `services`. Keep execution in `deployments`. Service API modules must not create Docker clients.

A runtime feature normally follows:

```text
Service configuration
 -> ServiceRevision/compiler
 -> ServiceRuntimeGraph
 -> SwarmRuntime
 -> Swarm Service
```

## Tests

Run:

```bash
pytest
```

The architecture-validation workflow compiles the whole `src/` tree.

## Documentation

Repository documentation belongs under `documentation/`. Do not add architecture/install documents beside source packages.
