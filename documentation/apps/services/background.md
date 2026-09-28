# services background and implicit behavior

## Revisioning
services.revisioning.ensure_revision_for_deploy reads durable Service desired state and creates an immutable ServiceRevision under transactional/locking rules. activate_revision_locked is the fenced activation boundary. active_revision is executable authority; selected_deploy is only a compatibility projection.

## Lifecycle fencing
lifecycle_generation is a monotonic compare-and-set fence. A worker holding an old generation must stop rather than overwrite newer desired intent. task_id is correlation/compatibility data, not sufficient ownership proof.

## Signals and cache
Service deletion coordinates Deploy cleanup. Volume deletion cleans runtime volume resources. PrivateNetwork deletion cleans runtime network resources. cache_signals invalidates service/network/volume namespaces. Runtime/cache cleanup must tolerate already-absent resources.

## Messenger dependency
services.share_cleanup checks live Messenger ConversationParticipant membership. Leaving/removal/group deletion can deactivate ServiceShare rows. This is an authorization dependency, not a client-side UI sync.

## Shell background behavior
ShellSession expiry closes idle sessions according to configured timeout. Shell tokens are capability credentials. ShellAuditEvent records activity but never grants permission.

## Runtime boundary
Start/stop/restart execution is owned by deployments Celery/runtime orchestration. services prepares desired state, revisions and policy; it is not a second Docker runtime.

## Tests
test_revisioning.py protects snapshot/immutability. Volume storage/quota tests protect ownership and detach/release semantics. Shell permission/policy/regression tests protect authorization, workspace and audit boundaries.