# 12 — Runtime log transport (Fluent Bit)

## Decision

PassDeployer uses **Fluent Bit** as the runtime log transport for Docker Swarm workloads.

The Docker Engine Fluentd logging driver forwards stdout/stderr over a host-local Unix domain socket. One Fluent Bit agent runs on each Docker node, batches the records and forwards them over a private Docker network to the Django ingestion endpoint. Django remains responsible for ownership validation, redaction, retention, quotas, durable storage, query APIs and WebSocket fan-out.

This avoids a Python thread and Docker log-follow connection for every application task. The Fluent Bit agent is bounded by default to 128 MiB RAM, 0.50 CPU, 32 MiB in-memory chunks and 512 MiB of filesystem buffering. Each task uses Docker's asynchronous, bounded, non-blocking logging mode so a stalled log backend does not block application stdout/stderr.

## Data path

```text
Application / Ready App / database task
        |
        | stdout + stderr
        v
Docker Engine: fluentd log driver
        |
        | host-local Unix socket
        v
Fluent Bit (one agent per node)
        |
        | gzip JSON Lines, authenticated HTTP
        v
Django /services/internal/logs/ingest/
        |
        +--> ownership and payload validation
        +--> secret redaction and entry-size limit
        +--> per-service rate and retention/quota policy
        +--> bulk insert / conflict-safe deduplication
        +--> deployment-log PostgreSQL
        +--> Channels realtime fan-out
```

The agent never receives the Docker socket and application containers never receive database credentials or the ingestion token. The internal ingestion endpoint is authenticated with a randomly generated, installation-local token kept in `.env`.

## New single-node Swarm installation or update

1. Keep `SWARM_ENABLED=1` and `LOG_INGEST_ENABLED=1` in `.env`. Do not set `LOG_INGEST_SHARED_TOKEN` manually; the Compose wrapper generates a 256-bit token the first time it starts the log agent.
2. Prepare/recreate the control plane with the repository wrapper:

   ```bash
   ./scripts/compose.sh up -d --build
   ```

   The wrapper creates the internal log network and host socket directory. The `runtime-logs` Compose profile starts Fluent Bit only when Swarm is active and runtime logging is enabled.
3. Review currently managed Swarm services before changing their logging driver:

   ```bash
   ./scripts/migrate-runtime-log-driver.sh
   ```

4. Apply the change when the dry-run list is correct:

   ```bash
   ./scripts/migrate-runtime-log-driver.sh --apply
   ```

   Swarm replaces the affected task generations using each service's existing update policy. Run this in a maintenance window if the workload has one replica and uses stop-first updates.
5. Deploy or restart one test service and confirm that its service Logs view receives both stdout and stderr. Also check **Wagtail → Logging health** and:

   ```bash
   ./scripts/compose.sh logs --tail=100 log-collector
   ```

   Docker's `docker service logs` API only supports `json-file` and `journald`; for Fluentd-managed Swarm services PassDeployer reads the canonical persisted log database instead.

New Swarm deployments receive the Fluentd driver automatically. Existing services are not mutated just because the control plane was updated; use the explicit migration command above.

## Multi-node Swarm

The Unix socket is node-local. There must be one Fluent Bit agent on every node where an application task can run.

1. Run `scripts/prepare-log-node.sh` on **every** eligible Linux node, using the same `LOG_FORWARD_SOCKET_PATH` from the manager's `.env`. The script creates a persistent systemd-tmpfiles rule so the directory returns after reboot.
2. Start/update the control plane on the manager so it joins the private attachable overlay network and creates the shared ingestion token.
3. Run on the manager:

   ```bash
   ./scripts/deploy-log-agents.sh
   ```

   This stops the single-node Compose agent and deploys the optional global Swarm stack. It places one bounded Fluent Bit task on each eligible Linux node. The script prints the node list; confirm the socket preparation succeeded on every node before migrating application services.
4. Use `./scripts/migrate-runtime-log-driver.sh` to preview, then `--apply` to migrate existing Swarm workloads.

The agent's filesystem queue is local to each node. It survives agent restarts on that node but is not a distributed queue; node loss can destroy buffered-but-not-yet-forwarded records on that node.

## Standalone Docker compatibility

When Docker Swarm is not active (or `SWARM_ENABLED=0`), the wrapper activates the `docker-logs` profile and retains the existing Python Docker log collector. Standalone Docker continues to use its local logging driver so internal helper containers that call `container.logs()` remain compatible.

## Rollback

For Swarm services, keep Fluent Bit running while changing the Docker logging driver back:

1. Set `LOG_INGEST_ENABLED=0` in `.env`.
2. Recreate the control-plane processes so workers read the disabled setting:

   ```bash
   ./scripts/compose.sh up -d --force-recreate web celery deployment-worker
   ```

3. Roll existing Swarm services back to Docker's local `json-file` driver:

   ```bash
   ./scripts/migrate-runtime-log-driver.sh --driver json-file --apply
   ```

4. Stop the Fluent Bit agent. For Compose mode:

   ```bash
   docker compose --profile runtime-logs -f compose.yaml stop log-collector
   ```

   For global Swarm mode:

   ```bash
   docker stack rm passdeployer-logs
   ```

5. When runtime logs are still required after rollback, start the compatible collector explicitly:

   ```bash
   docker compose --profile docker-logs -f compose.yaml up -d legacy-log-collector
   ```

The migration command is dry-run by default. It changes only Swarm services carrying PassDeployer's `managed-by` and `passdeployer.service` ownership labels.

## Operational boundaries

- `DeployLog` lifecycle events remain on their existing event sink/outbox path; Fluent Bit transports container stdout/stderr only.
- No log text is written into Redis as the durable store.
- The HTTP ingestion endpoint validates the shared token and Docker ownership labels before resolving the Service row.
- The endpoint limits body size and batch size, strips line terminators, redacts secrets, and applies the service's existing logging policy.
- Duplicate/retried records use the existing stream fingerprint and sequence constraints. A batch insert is transactionally grouped and updates usage counters once per batch.
- Docker's non-blocking per-container buffer and the Fluent Bit disk queue are bounded. If both queues fill, log lines can be dropped rather than consuming unbounded host memory or blocking the app. Monitor the logging-health dropped counters and Fluent Bit output errors.
