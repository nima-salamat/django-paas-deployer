# Architecture

PassDeployer is a service-centric Django PaaS whose customer workload execution uses Docker Swarm in the normal runtime path.

## Cross-app architecture

Start with [apps/README.md](apps/README.md) for the canonical Django application graph. The main ownership split is:

~~~text
users             -> canonical identity
auth_users        -> credential/session/authentication state
plans             -> customer resource/logging policy
services          -> durable Service intent + immutable revisions
deploy            -> Deploy provenance + deployment/base-image/operator records
deployments       -> build/planning/runtime/lifecycle/reconciliation execution
logs              -> runtime/service log persistence and ingestion
app_catalog       -> catalog interpretation + multi-Service installation coordinator
messenger         -> messaging/realtime domain
tickets           -> support workflow
custom_emails     -> email template/delivery domain
docs              -> product documentation content
core              -> shared infrastructure/settings/cache/media
cms               -> Wagtail integration
~~~

## Control-plane path

~~~text
HTTP / WebSocket
 -> Django / DRF / Channels
 -> owning application domain
 -> Celery for asynchronous work
 -> deployments for runtime work
 -> Docker Engine / Swarm
 -> observations/events
 -> durable domain state / realtime notification
~~~

Domain APIs retain authorization and durable state. They do not become alternate runtime engines.

## Service/deployment ownership

~~~text
Service desired state
 -> ServiceRevision (immutable)
 -> Deploy (execution/provenance)
 -> deployments planning/build/runtime
 -> Docker/Swarm observation
~~~

Service.active_revision is the current executable release. selected_deploy remains compatibility projection. See apps/services and apps/deploy plus deployments/01-system-model.md and 03-execution-lifecycle.md.

## Runtime truth versus desired state

The database stores desired state/provenance. Docker/Swarm observations describe what actually exists. Reconciliation compares the two and fails closed when runtime identity is unknown rather than silently adopting it.

## Storage

Docker local volumes are node-local. Managed local-volume workloads may be pinned to the volume owner node; this does not provide shared-storage HA.

## Logging split

Runtime service logs are owned by logs. Deployment lifecycle events are DeployLog records in the separate deployment-log database.

## Wagtail

Wagtail is an administration/presentation layer. Domain apps retain ownership and permission rules. Runtime-authoritative fields should remain controlled by domain workflows.

## Transitional compatibility

SWARM_ENABLED=0 remains a legacy compatibility runtime mode. Core deployment execution is documented in deployments/.
