# services background and implicit behavior

## Revisioning
services.revisioning.ensure_revision_for_deploy reads durable Service desired state and creates an immutable ServiceRevision under transactional/locking rules. activate_revision_locked is the fenced activation boundary. active_revision is executable authority; selected_deploy is only a compatibility projection.

## Lifecycle fencing
lifecycle_generation is a monotonic compare-and-set fence. A worker holding an old generation must stop rather than overwrite newer desired intent. task_id is correlation/compatibility data, not sufficient ownership proof.

## Signals and cache
Service deletion is the ownership boundary for service runtime cleanup. Before deleting the Service row, its signal requests canonical deployment cancellation for every PENDING/RUNNING/ROLLING_BACK Deploy owned by the service, then removes only service-owned runtime resources. Database-plan services use DBDeployer teardown; ordinary services use the Swarm/container ownership path. Exclusive service volumes are removed only after runtime cleanup succeeds, so a failed Docker volume deletion keeps the durable ownership row.

Service deletion also removes service-scoped deployment/runtime log records stored in `DEPLOYMENT_LOG_DB_ALIAS`. Those models intentionally use scalar service ids, so this cleanup cannot be provided by the primary database cascade.

ServiceRevision deletion removes its revision-owned source artifact from file storage before the durable row disappears. PrivateNetwork deletion requires that no service references the network through either the primary Service.network relation or ServiceNetworkAttachment and removes only a Docker network carrying the PassDeployer ownership label. Runtime/cache cleanup tolerates already-absent resources but does not silently delete unmanaged resources.

cache_signals invalidates service/network/volume namespaces after ORM changes.

## Messenger dependency
services.share_cleanup checks live Messenger ConversationParticipant membership. Leaving/removal/group deletion can deactivate ServiceShare rows. This is an authorization dependency, not a client-side UI sync.

## Shell background behavior
ShellSession expiry closes idle sessions according to configured timeout. Shell tokens are capability credentials. ShellAuditEvent records activity but never grants permission.

## Runtime boundary
Start/stop/restart execution is owned by deployments Celery/runtime orchestration. services prepares desired state, revisions and policy; it is not a second Docker runtime.

## Tests
test_revisioning.py protects snapshot/immutability. Volume storage/quota tests protect ownership and detach/release semantics. Shell permission/policy/regression tests protect authorization, workspace and audit boundaries.