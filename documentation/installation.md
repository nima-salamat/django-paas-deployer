# Installation

This guide describes deployment of the PassDeployer control plane and Docker runtime dependencies.

For multi-node Swarm, local persistent volumes are provisioned through the Django volume registry and pinned to the provisioning node. A conflicting explicit node.id placement rule is rejected for managed local volumes.

Tenant storage quota is a logical Service policy; standard Docker local volumes do not provide a hard per-volume filesystem quota. Runtime usage is measured when the Docker backend can report it and warnings follow operator settings.

Canonical storage/domain semantics are now under [apps/services/models.md](apps/services/models.md) and the deep runtime discussion in [deployments/05-runtime-and-swarm.md](apps/deployments/execution/05-runtime-and-swarm.md).

## Legacy mode

SWARM_ENABLED=0 remains an explicit compatibility mode. The normal architecture is Swarm-first.


## Optional: use the existing Matrix PostgreSQL server

This mode runs one PostgreSQL **server/container** for Matrix and the Deployer control plane. Shared mode requires Docker Compose v2.20.0 or newer because it uses optional `depends_on` dependencies. It does **not** merge their data into one database: Synapse keeps its existing `synapse` database, while Deployer uses two separate databases (`paas_deployer` and `paas_deployer_logs`) and a separate `paas_deployer` login. The local Deployer PostgreSQL services are disabled only when `USE_MATRIX_POSTGRES=1` is used with `./scripts/compose.sh`.

### Safety first — back up Matrix before changing anything

Run these commands on the VPS. If the dump command fails or creates an empty file, stop here and fix the backup before proceeding. Keep this SQL dump private; it can contain sensitive database metadata.

```bash
set -eu
install -d -m 700 /opt/backups/matrix
umask 077
backup="/opt/backups/matrix/matrix-before-paas-postgres-sharing-$(date +%F-%H%M%S).sql"
docker exec synapse-postgres pg_dumpall -U synapse > "$backup"
test -s "$backup"
chmod 600 "$backup"
printf 'Backup written: %s\n' "$backup"
```

`MATRIX_POSTGRES_HOST` is the DNS name used by Django, while `MATRIX_POSTGRES_CONTAINER` (optional) is the exact Docker container name used only for network inspection. The wrapper first tries to discover a running container by the configured hostname/network alias; set `MATRIX_POSTGRES_CONTAINER` only if discovery is ambiguous or the hostname is not advertised as a Docker alias. It then checks that the configured network contains the resolved container before starting shared mode. If the configured name is stale but exactly one suitable network can be identified (preferring a network shared with the `synapse` container), it selects that network for this Compose invocation. If there are multiple possible networks, it stops and prints the actual network membership instead of letting Django enter a migration/restart loop. You can still set `MATRIX_DOCKER_NETWORK` explicitly in `.env` when detection is ambiguous. To inspect the current setup manually, run the commands below:

```bash
docker network ls --filter name=matrix --format '{{.Name}}'
docker inspect synapse-postgres --format '{{range $name, $cfg := .NetworkSettings.Networks}}{{println $name}}{{end}}'
```

Do not remove/recreate the Matrix PostgreSQL container, rename its data mount, run `docker compose down -v` in the Matrix project, or use the `synapse` database for Deployer.

### Create isolated Deployer databases on the existing server

Generate a new password containing only hex characters:

```bash
openssl rand -hex 32
```

Copy it somewhere secure temporarily, then open a psql session to the **existing** Matrix PostgreSQL container:

```bash
docker exec -it synapse-postgres psql -U synapse -d postgres
```

At the psql prompt, run these one at a time. The `\password` command prompts for the new password without embedding it in SQL history; enter the generated password twice.

```sql
CREATE ROLE paas_deployer LOGIN;
\password paas_deployer
CREATE DATABASE paas_deployer OWNER paas_deployer;
CREATE DATABASE paas_deployer_logs OWNER paas_deployer;
\l
\du paas_deployer
```

If role/database creation fails or the `synapse` role lacks permission, stop and share only the error text—not any password or token. Do not modify the existing `synapse` database or change the Synapse role to make this work.

### Enable the option

Add/update only these lines in the current Deployer `.env`; do not replace your existing `.env` with `.env.example`. Put the same generated password into `MATRIX_POSTGRES_PASSWORD`.

```dotenv
USE_MATRIX_POSTGRES=1
MATRIX_POSTGRES_HOST=synapse-postgres
# Optional: exact Docker container name if it differs from the host alias
MATRIX_POSTGRES_CONTAINER=
MATRIX_POSTGRES_PORT=5432
MATRIX_POSTGRES_USER=paas_deployer
MATRIX_POSTGRES_PASSWORD=PASTE_THE_GENERATED_HEX_PASSWORD_HERE
MATRIX_POSTGRES_MAIN_DB=paas_deployer
MATRIX_POSTGRES_LOG_DB=paas_deployer_logs
```

Leave the current Deployer `DB_HOST=db`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DEPLOYMENT_LOG_DB_HOST=deployment-log-db` and other local-DB settings unchanged. The wrapper maps the Matrix-specific settings only while shared mode is on, so switching the flag back to `0` is a straightforward rollback. The backend containers must be able to reach the existing network configured by `MATRIX_DOCKER_NETWORK`.

Start with the wrapper (it chooses the overlay and remaps database settings only when the flag is enabled):

```bash
./scripts/compose.sh up -d --build
./scripts/compose.sh logs --tail=100 web
./scripts/compose.sh exec web python manage.py check
./scripts/compose.sh exec web python manage.py showmigrations logs --database=deployment_logs
```

Verify both configured Django database aliases point to the intended databases:

```bash
./scripts/compose.sh exec web python -c '
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connections
for alias in ("default", "deployment_logs"):
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user")
        print(alias, cursor.fetchone())
'
```

The output should show `paas_deployer` for `default` and `paas_deployer_logs` for `deployment_logs`, both using `paas_deployer`. Synapse continues using its unchanged `synapse` database.

**Only after both Deployer database checks pass and Synapse is healthy**, stop the two old Deployer PostgreSQL containers to free their RAM:

```bash
docker stop deploy-db deploy-log-db
```

This stops only the old Deployer containers. It does not remove any container volume, and does not touch the Matrix container or Matrix data. Keep the old Deployer volumes until you are fully satisfied with the new setup; no cleanup is needed to achieve one running PostgreSQL server.

### Rollback

Set `USE_MATRIX_POSTGRES=0` in the Deployer `.env` and run `./scripts/compose.sh up -d`. The wrapper returns to the existing local Deployer database services. Their old volumes were intentionally not deleted, so they remain available for rollback. Do not use `docker compose down -v` as part of this switch.
