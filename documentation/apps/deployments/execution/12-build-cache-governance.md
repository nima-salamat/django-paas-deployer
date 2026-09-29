# Build cache governance

PassDeployer separates physical Docker BuildKit storage from logical tenant
application-image retention.

The global policy measures the physical BuildKit cache from Docker's daemon
usage API and applies an operator-defined retention period plus a storage
target through Docker's build-prune API. This is shared infrastructure, so
the platform must not pretend that shared BuildKit blobs are private to one
tenant.

User and service quotas apply to tracked application image artifacts. The
artifact records are linked to the owning User, Service and Deployment. Active
deployments, the selected/active revision, pinned records, and the configured
newest successful deployments are protected. Non-protected artifacts are
reclaimed oldest-first when they exceed quota or retention.

Default policy:
- Global BuildKit limit: 20 GB
- Default user application-image quota: 5 GB
- Default service application-image quota: 2 GB
- Retention: 30 days
- Protected successful deployments: 3
- Cleanup target after global GC: 80%
- Maintenance cadence: 30 minutes

Application builds may use recent local application-image references from the
same service as server-owned cache sources. Tenants cannot choose arbitrary
cache sources.

Base runtime images remain operator-owned shared infrastructure and keep the
existing fingerprint and deployment-lease protections. They are excluded from
user/service cache quotas.

Tenant quota numbers are logical artifact accounting; the global BuildKit
number is the physical shared cache measurement. They are intentionally not
expected to be equal when layers are shared.
