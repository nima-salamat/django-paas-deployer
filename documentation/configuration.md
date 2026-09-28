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

This installation currently supports the Docker `local` volume backend for managed tenant volumes. The backend is platform-controlled; tenant deployment configuration cannot inject arbitrary Docker driver names or `driver_opts`. The runtime carries `driver=local` through the VolumeSpec into Docker provisioning. A future non-local backend must add an explicit operator-controlled backend definition before it is enabled.

`Volume.size_mb` is the logical allocation used by Service/Plan quota checks. The default Docker `local` backend is reported as LOGICAL_ONLY because this installation does not configure a verified per-volume hard-quota mechanism.

Volume lifecycle is explicit:
**DETACH** clears mount metadata but keeps Service ownership and therefore keeps logical quota charged.
**RELEASE** clears Service ownership and frees logical quota, but intentionally retains the physical Docker volume for a bounded retention period.
**DELETE / RECLAIM** removes the physical Docker volume and then removes the registry row.

The operator setting `volume_release_retention_days` defaults to 30 days. A Celery reclaim task runs hourly and reclaims expired released volumes. Reclaim checks the managed-volume ownership label and verifies Docker deletion before deleting the registry row. A reclaim failure leaves the registry row in place with `reclaim_error`, so physical storage cannot silently disappear from accounting.

The platform exposes deployment-time usage inspection and warnings; this is not continuous tenant storage monitoring. Reconciliation separately classifies active tenant storage, retained released storage, orphan storage, and unknown/unaccounted storage.

## Base runtime images

Base runtime images are operator-owned infrastructure. The canonical PHP/Apache image is `paas-base/php-apache:<version>-r1`; PHP no longer selects a `-root` repository based on application semantics. The application Dockerfile owns the final DocumentRoot.

The operator can use Wagtail's **Base runtime images** screen to **Build / Ensure available** or **Renew / Rebuild** a base image. Build reuses a compatible READY image. Renew forces a fresh build. Both actions enqueue the existing Celery `base-images` task and participate in the same database ownership/fencing lifecycle as automatic deployment builds.

Base image rows are keyed by logical runtime, version, variant, architecture and Docker host. This means concurrent deployments share a build on the same Docker daemon; different Docker daemons require their own base image unless the resulting application image is published to a registry for Swarm distribution.

Base image lifecycle timing is separate from application deployment timing. The operator setting `base_image_build_timeout_minutes` defaults to 10 minutes and controls the base build/shared-wait phase. `deploy_timeout_minutes` independently controls the application phase. The legacy `monitor_stale_base_build_minutes` name remains only as a compatibility alias and no longer provides a separate timeout policy.

Base image reuse requires a matching `definition_fingerprint` and Docker label `io.passdeployer.base-definition`. Changing the operator-owned definition invalidates the cached image even when the human-readable tag remains unchanged.
