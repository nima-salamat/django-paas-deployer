# deploy background behavior

DeployLog writes target the separate deployment_logs database. Deploy serialization treats failure to reach that auxiliary database as a best-effort degradation, returning an empty recent_logs representation while emitting a server warning.

BaseRuntimeImage build/reuse behavior is a shared execution concern. BaseRuntimeImageLease protects an artifact from cleanup while a deployment uses it. The build task records task ownership so a stale builder cannot fail a newer build.

Deploy deletion can remove uploaded deployment archives. Deleting a Deploy is not equivalent to stopping a runtime Service; runtime lifecycle remains in deployments.

Wagtail/admin controls in deploy expose operator infrastructure state with guarded editing. See ../deployments/execution/08-base-images.md and ../deployments/execution/06-workers-concurrency-and-state.md.

Tests are split between src/deploy/tests.py and the deployment contract suite; use both when changing persistence/runtime boundaries.
