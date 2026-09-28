# deploy background behavior

DeployLog writes target the separate deployment_logs database. Deploy serialization treats failure to reach that auxiliary database as a best-effort degradation, returning an empty recent_logs representation while emitting a server warning.

BaseRuntimeImage build/reuse behavior is a shared execution concern. BaseRuntimeImageLease protects an artifact from cleanup while a deployment uses it. The build task records task ownership so a stale builder cannot fail a newer build.

Deploy deletion can remove uploaded deployment archives. Deleting a Deploy is not equivalent to stopping a runtime Service; runtime lifecycle remains in deployments.

Wagtail/admin controls in deploy expose operator infrastructure state with guarded editing. See ../deployments/execution/08-base-images.md and ../deployments/execution/06-workers-concurrency-and-state.md.

Tests are split between src/deploy/tests.py and the deployment contract suite; use both when changing persistence/runtime boundaries.

## Management commands

### migrate_deployment_logs

Source: src/deploy/management/commands/migrate_deployment_logs.py.

Copies legacy DeployLog rows from the primary database to DEPLOYMENT_LOG_DB_ALIAS in batches. --batch-size defaults to 500 and is clamped to at least one. --delete-source deletes each source batch only after its destination transaction succeeds. The command is intended for one-time operational migration and is rerunnable because destination writes use update_or_create by log id.

### setup_deployment_log_db

Source: src/deploy/management/commands/setup_deployment_log_db.py.

Ensures the DeployLog table exists and adds missing local columns on the deployment-log database, then applies the logs app migrations on that database alias. It is an operator bootstrap/repair command and should run only against the configured deployment-log database.
