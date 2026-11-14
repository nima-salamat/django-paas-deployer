# Ready App runtime controls

Ready Apps are application-level installations composed of multiple managed
Service/Deploy pairs. Their runtime lifecycle must be controlled through the
parent ApplicationInstance so the saved dependency graph remains authoritative.

## API

- `POST /api/application-catalog/installations/<uuid>/start/`
- `POST /api/application-catalog/installations/<uuid>/stop/`

The endpoints are owner-scoped and return the updated ApplicationInstance.
Accepted asynchronous operations return HTTP 202. Repeated Stop All requests
while the same stop operation is active are idempotent.

## Start All

Start All reuses the immutable orchestration snapshot captured at installation
time and the existing ApplicationStackExecutor scheduler. Stopped or failed
children are reset for a new attempt; already-running children with a successful
Deploy are retained. The scheduler dispatches the ready DAG frontier and only
starts dependent services after their dependencies reach successful deployment
state.

The parent enters `deploying` with `runtime_operation=start`. Completion
returns it to `running`; an unsuccessful restart leaves it `degraded` with
an error message.

## Stop All

Stop All walks the reverse topological order of the saved application graph.
It dispatches one child stop at a time. The next dependency is not stopped
until the current dependent Service is confirmed as `stopped` with desired
state `stopped`.

The parent enters `stopping` with `runtime_operation=stop`. Completion
sets it to `stopped`. If a child cannot be confirmed stopped, the coordinator
halts, leaves its dependencies running, and marks the parent `degraded`.
The durable parent operation and periodic reconciliation recover work after
a broker or worker interruption.

## Ownership and individual actions

A child Service/Deploy remains owned by its ApplicationInstance through
ApplicationInstanceService. Individual child deletion is rejected by the
service APIs and the database relation uses `on_delete=RESTRICT`; delete the
parent installation to clean up the complete managed stack.

Individual user/admin Start, Stop, Restart, rebuild, and runtime-purge requests
for a managed child return HTTP 409 (`catalog_service_managed`). Use the
parent Ready App controls instead. This prevents a child action from bypassing
dependency ordering or removing a runtime that the parent still owns.
