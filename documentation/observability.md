# Observability

## Logs

The `logs` app owns persisted deployment/runtime log data, retention and usage reconciliation.

Deployment lifecycle events use the `DeploymentLogger` / event sink / outbox path and remain independent of container stdout/stderr.

For Docker Swarm workloads, Docker's Fluentd logging driver forwards stdout/stderr to a host-local Unix socket. One bounded Fluent Bit agent per node batches the records and sends them to the authenticated Django ingestion endpoint. Django validates service ownership, redacts secrets, applies each service's quota/rate/retention policy, bulk-writes the dedicated log database and publishes realtime Channels batches. The agent does not mount the Docker socket and does not write directly to PostgreSQL.

On a single-node installation, Compose starts the Fluent Bit agent with the `runtime-logs` profile. Multi-node Swarm uses the optional global stack in `deploy/fluent-bit/swarm-stack.yaml`; each node must have the configured host socket directory prepared first. See [Runtime log transport](apps/deployments/execution/12-runtime-log-transport.md) for rollout and rollback procedures.

Existing Swarm services are not changed automatically: preview with `./scripts/migrate-runtime-log-driver.sh`, then use `--apply` to roll their task generation onto Fluent Bit. For standalone Docker mode, the legacy Python Docker log collector remains available through the `docker-logs` Compose profile.

Docker's `service logs` API only supports `json-file` and `journald`. PassDeployer therefore reads persisted service-log rows for services using Fluentd rather than trying to call `docker service logs` on them.

## Runtime state

Service runtime APIs can report desired/running replicas, task states and local CPU/memory when the task exists on the connected Docker Engine.

## WebSockets

Channels publishes realtime events. The durable state remains in PostgreSQL/Docker. Browser clients authenticate first-party sockets with session-bound access JWTs, and reconnect after access-token refresh when a socket closes with `4401`; session revocation is enforced by heartbeat revalidation.

## Shell

Shell resolves the actual Swarm task container. Exec is allowed only if that task is on the connected Docker node.

## Health

Readiness combines Swarm task/service state with configured application healthchecks.
