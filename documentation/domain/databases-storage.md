# Databases and Storage

## Database resources

`DatabaseResource` describes a managed/external database resource. `ServiceDatabaseBinding` connects it to an application Service.

## Runtime

Managed database engines also run as Swarm Services.

The database layer remains specialized for image selection, initialization, readiness and credential reconciliation, but Swarm owns runtime scheduling.

## MySQL/MariaDB

Credential reconciliation runs against the actual ready Swarm task container.

## Local storage

Docker local volumes are node-local. Services using them are pinned to the volume owner unless an explicit node-id rule overrides the placement.

## Reinitialization

Database `force_reinit` removes/recreates managed data volumes and must be treated as destructive.
## Tenant volume storage contract

`Volume.size_mb` is the declared logical capacity used by the Django Service storage quota. It is not, by itself, a physical filesystem quota. The default Docker `local` volume driver is therefore LOGICAL_ONLY / UNENFORCED for per-volume capacity in the standard installation.

During deployment the platform asks Docker Engine for actual volume usage through its system disk-usage API. When measurable usage reaches the operator-controlled `VOLUME_USAGE_WARNING_PERCENT` threshold (90% by default), a warning is written through the existing deployment event pipeline and is visible in the deployment `recent_logs`. Usage at or above 100% is reported as critical; the platform does not claim that a write was physically blocked when the backend has no hard quota.

Unknown usage is represented as unavailable, never as zero. A backend that cannot provide a reliable usage value is not treated as a hard-limited volume.

### Local Swarm storage

Docker `local` volumes are node-local. In Swarm deployments the project pre-provisions managed persistent volumes through the Django volume registry and, when `SWARM_LOCAL_VOLUME_PIN=1`, pins local-volume workloads to the Docker node that provisioned the volume. An explicit conflicting `node.id` placement constraint is rejected instead of allowing Docker to create a same-named volume on another node.

### Hard physical quotas

The standard installation does not configure a filesystem quota backend for Docker local volumes. Do not configure `driver_opts` with an assumed `size` option and consider the volume hard-limited unless the selected storage backend documents and is verified to enforce that capacity. Docker's local driver accepts driver-specific mount options; a driver option is not proof of enforcement.

Hard enforcement requires a storage backend that provides an actual capacity mechanism, such as a verified filesystem quota integration or an appropriate storage/plugin backend. That backend is not bundled by PassDeployer today because the repository does not contain the host-level setup, node-wide quota lifecycle, or runtime verification needed to make such a claim.

### Host-space preflight

`Volume.check_host_space()` is a best-effort Docker-root filesystem safety check, not a reservation and not a per-volume quota. The check is fail-closed when the Docker root filesystem cannot be inspected.

### Persistent database/application defaults

Automatic database and application persistent volumes are registry-backed. A storage quota or registration failure is terminal for the deployment rather than silently falling back to an anonymous Docker volume. This prevents a successful deployment from silently losing persistence across rebuilds.

### Verification

Use the Docker daemon on the node that owns the volume to inspect its driver and reported usage. `docker system df -v` exposes local-volume usage, while the Engine `GET /system/df` API is the programmatic source used by the platform. For Swarm, verify that the task node matches the local-volume owner before treating a usage reading as authoritative.
## Operator verification

Run these commands on the Docker daemon node that owns the local volume:

```bash
docker info --format '{{.DockerRootDir}} {{.Driver}}'
docker volume inspect <docker-volume-name>
docker system df -v
docker volume ls --filter dangling=true
```

For the filesystem that contains Docker's volume data, verify type and mount options:

```bash
findmnt -no TARGET,FSTYPE,OPTIONS --target /var/lib/docker
df -hT /var/lib/docker
stat -f -c 'type=%T mount=%m' /var/lib/docker
```

When evaluating an XFS-backed hard-quota design, verify the host actually has project quota support and enforcement enabled:

```bash
findmnt -no TARGET,FSTYPE,OPTIONS --target /var/lib/docker
xfs_info /var/lib/docker
xfs_quota -x -c 'state' /var/lib/docker
xfs_quota -x -c 'report -p' /var/lib/docker
```

On a multi-node Swarm, verify where the workload actually runs:

```bash
docker service ps <service-name> --no-trunc
docker node inspect <node-id> --format '{{.Description.Hostname}}'
docker volume inspect <docker-volume-name>
```

The last step matters for node-local volumes: a manager-side Docker inspection is not proof that a workload's volume on another node has the same physical storage state.
