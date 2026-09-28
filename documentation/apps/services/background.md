# services background and implicit behavior

## Revisioning

services.revisioning.ensure_revision_for_deploy reads the durable Service configuration and creates an immutable ServiceRevision under transactional/locking rules. A revision captures the executable snapshot needed for deterministic planning; later Service edits do not rewrite historical revisions.

## Lifecycle fencing

lifecycle.fencing stores/captures lifecycle_generation and provides compare-and-set desired-state updates. A worker holding an old generation must stop rather than overwrite newer lifecycle intent.

lifecycle.authority provides the canonical active revision/deploy projection helpers. selected_deploy is synchronized from active revision for compatibility but is not the authority.

## Signals

service deletion coordinates related Deploy deletion. Volume deletion cleans Docker volume resources; PrivateNetwork deletion cleans its runtime network. cache_signals invalidates service/network/volume namespaces after changes.

## Scheduled work

Shell-session expiry/reclamation is configured through Beat. Runtime start/stop/restart dispatches are performed by Celery and deployments; services does not own the external runtime lifecycle.

## Tests as contracts

test_revisioning.py protects snapshot/immutability; volume quota tests protect ownership/soft-detach semantics; shell permission/policy/regression tests protect shell authorization, workspace and audit boundaries.
