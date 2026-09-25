# Configuration

## Layers

1. Environment variables configure bootstrap and infrastructure connectivity.
2. Operator settings define server-owned runtime/build policy.
3. Tenant configuration defines application behavior.

Tenant JSON must never become arbitrary Docker host policy.

## Core variables

Important installation variables include:

`SECRET_KEY`, `DEBUG`, `DOMAIN_NAME`, `API_DOMAIN_NAME`, database variables, Redis/Celery variables and the `SWARM_*` settings.

## Swarm variables

- `SWARM_ENABLED`
- `SWARM_CLUSTER_NAME`
- `SWARM_IMAGE_REGISTRY`
- `SWARM_IMAGE_NAMESPACE`
- `SWARM_LOCAL_VOLUME_PIN`

## Paths

Source code is under `src/`.

Runtime data remains outside source:

- `staticfiles/` for collected static output
- `media/` for uploads/runtime media

The settings module uses the repository root as the data/artifact root.

## Admin paths

`WAGTAIL_ADMIN_PATH` and `DJANGO_ADMIN_PATH` are validated as URL-safe single path segments.

## Secrets

Runtime secrets are versioned and referenced by revisions. Revision APIs never return plaintext secret values.

Build-scoped secrets are currently rejected because the build backend does not provide secure BuildKit secret mounts.
