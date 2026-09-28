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
## Volume storage

`VOLUME_USAGE_WARNING_PERCENT` is an operator-only threshold for real Docker volume usage warnings. The default is 90%. It controls observability only; it does not enable a filesystem quota.

`Volume.size_mb` is the logical allocation used by Service/Plan quota checks. The default Docker `local` backend is reported as LOGICAL_ONLY because this installation does not configure a verified per-volume hard-quota mechanism.
## Base runtime image lifecycle

Base runtime images are operator-owned infrastructure artifacts. The canonical PHP base is `paas-base/php-apache:<version>-r1`; application-specific Apache DocumentRoot selection is applied later in the application Dockerfile. Plain PHP and PHP frameworks therefore share one PHP base identity.

The operator-controlled `base_image_build_timeout_minutes` setting has a default of 10 minutes. It is the dedicated budget for building or waiting for a required base image. `deploy_timeout_minutes` is a separate 10-minute default application-phase budget that starts after required base images become ready.

Missing or incompatible base images are built through the dedicated `base-images` Celery queue. Concurrent deployments targeting the same base identity on the same Docker daemon observe the `BUILDING` registry row and wait instead of starting another build. A manual **Renew / Rebuild** request made during an active build records one follow-up rebuild request rather than replacing the current owner.

Wagtail exposes **Build / Ensure available** and **Renew / Rebuild** controls for Base Runtime Images. These controls only queue the existing Celery lifecycle; Docker builds are never performed in the Wagtail HTTP request.

Base Runtime Image identity is scoped by logical runtime, runtime version, variant, architecture and Docker host. Therefore shared build ownership is **per Docker daemon**, not a cluster-wide Docker volume/cache lock. In multi-node Swarm, application images are distributed through `SWARM_IMAGE_REGISTRY` when configured, while the base-image build registry itself remains host-scoped.

The `definition_fingerprint` stored on `BaseRuntimeImage` and the `io.passdeployer.base-definition` image label remain authoritative. A local image with the same tag but an incompatible or missing fingerprint is not adopted as READY.

The historical `apache-root` / `apache-public` PHP identities are treated as legacy compatibility records during migration. Existing Docker images are not blindly deleted; active references/builds are preserved while new deployments converge on the canonical `paas-base/php-apache` identity.
