# Deployments architecture audit

Status: investigation and redesign proposal

Branch: refactor/service-centric-runtime

Audit date: 2026-09-25

This document records the repository-backed audit of the deployment subsystem. It is deliberately a design deliverable, not an implementation of the proposed redesign. No merge to master is implied by this document.

## Executive finding

The repository already contains the foundations of a service-centric control plane:

- Service owns user intent and desired state.
- ServiceRevision is intended to be an immutable executable snapshot.
- Deploy records deployment intent, execution provenance, and compatibility state.
- StateManager provides transactional lifecycle transitions and worker fencing.
- ServiceRuntimeGraph is a useful runtime-neutral representation of process, endpoint, volume, and network intent.
- Swarm cluster and node models distinguish some desired fields from observed fields.

Those foundations are not yet the execution architecture. The live path still contains three materially different deployment implementations: Swarm services, legacy local Docker containers, and a separately routed database deployer. Runtime selection is driven primarily by the process environment, while database, Wagtail, static settings, service, revision, and deployment configuration overlap. The largest modules combine planning, build, runtime execution, health, rollback, cleanup, persistence, and eventing.

The result is not one monolith but a distributed monolith: responsibilities are split across files while remaining coupled through low-level Docker imports, a large DeploymentConfig, global switches, compatibility fields, and duplicated state updates.

The recommended redesign is incremental. First establish one configuration-resolution and runtime-selection boundary around the existing Swarm implementation. Then compile a validated DeploymentPlan, route application and database deployments through a shared lifecycle contract, and move API/reconciliation actions behind application services. The current Swarm behavior should be wrapped and characterized before it is decomposed.

## 1. Scope and evidence

The audit covered:

- src/deployments/, including Celery tasks and schedules, the orchestrator, Swarm runtime, database deployer, build and project modules, state, health, cleanup, logging, and managers.
- src/deploy/, including models, serializers, views, naming, state bridges, events, routers, and Wagtail admin.
- src/services/, including service, process, revision, secret, endpoint, volume, database, lifecycle, shell, and signal code.
- src/config/, src/core/, settings services, static configuration, Wagtail settings, and database routing.
- deployment documentation, Compose/Docker integration, migrations, tests, and the service/revision/reconciliation documentation.

The current branch is clean at 1463e19 and has origin/master (a221d3c) as its merge base. The report describes the code as it exists on this branch; it does not assume that the desired architecture is already implemented.

## 2. Current architecture

### 2.1 Real execution flow

The principal application deployment path is currently:

~~~
HTTP POST /deploy/
    |
    v
DeployViewSet.create (src/deploy/apis.py)
    |  parses config, derives platform, checks permissions and database inputs
    v
DeploySerializer.create (src/deploy/serializers.py)
    |  allocates a service-scoped name and creates Deploy
    v
DeployViewSet.start / Celery deploy task (src/deployments/celery/tasks.py)
    |  selects the database or application path
    v
DeployService.execute (src/deployments/celery/services/deploy_service.py)
    |  locks service, owns worker lease, materializes revision and resolves config
    v
ServiceRuntimeGraph + DeploymentConfig + DeployFacade
    |
    v
DeploymentOrchestrator (src/deployments/core/orchestrator.py)
    |  validation, archive extraction, platform detection, Dockerfile, image, runtime,
    |  health, activation, rollback and cleanup
    +------------------------------+
    |                              |
    v                              v
SwarmRuntime                    Container/Image/Network/Volume managers
(src/deployments/core/swarm.py) legacy local Docker path
    |                              |
    +---------------+--------------+
                    v
             Docker SDK / Swarm service and task
                    |
                    v
     DBAndChannelEventSink / DeploymentEventPipeline
        |                 |
        v                 v
    DeployLog          Channels/WebSocket + Deploy progress
                    |
                    v
     monitor_services_reconciliation / sync_swarm_infrastructure
       (src/deployments/celery/schedules.py)
                    |
                    v
        observed runtime inspection and repair attempts
~~~

Database deployments branch earlier:

~~~
DeployViewSet / deploy Celery task
    -> run_db_deploy
    -> DBDeployer (src/deployments/core/db_deployer.py)
    -> direct Docker or Swarm operations
    -> separate database-specific state, credentials, init, health and cleanup paths
~~~

This branch is specialized for good reasons, but it does not currently implement a shared strategy contract. It duplicates enough lifecycle and runtime behavior that changes to ownership, retry, rollback, or reconciliation must be considered in both paths.

### 2.2 Responsibilities by current module

| Area | Current implementation | Observed responsibility mix |
| --- | --- | --- |
| Presentation | src/deploy/apis.py, serializers.py | HTTP serialization, permissions, config parsing, platform validation, deployment actions, direct runtime cleanup, rollback/cancel state changes |
| Deployment application service | DeployService | Locking, worker ownership, revision materialization, compatibility normalization, policy resolution, build/runtime config assembly, orchestration, activation, legacy synchronization |
| Lifecycle state | core/state/manager.py, common/state_machine.py, deploy/deployment_state.py, monitor actions, legacy service status wrappers | Multiple transition and progress paths despite a stated single authoritative manager |
| Build | core/dockerfile.py, core/project_model.py, core/platform_bridge.py, core/manager/image_manager.py | Platform detection, source inspection, Dockerfile generation, build arguments, image cache/lease, registry behavior |
| Runtime execution | core/orchestrator.py, core/swarm.py, manager classes, db_deployer.py | Runtime selection, resource compilation, Docker calls, readiness, rollback, cleanup, logs and statistics |
| Runtime observation | core/swarm.py, celery/schedules.py, run_log_collector.py, event command | Swarm inspection, legacy container inspection, task recovery, service reconciliation, log discovery and ingestion |
| Configuration | Django settings, environment, CoreSettings, SystemSetting, static global config, Plan, Service, Revision, Deploy | Several overlapping sources with implicit precedence and no uniform explanation of the winning value |
| Operator controls | Wagtail admin models and CoreSettings | Some desired cluster/node controls, but no explicit runtime registry, capabilities, backend policy, or subsystem availability model |

## 3. Deployment creation and execution trace

### 3.1 Creation

DeployViewSet.create in src/deploy/apis.py accepts multipart or JSON input, loads the service, derives the deployment family from the service plan, sanitizes tenant configuration, performs database-specific validation, and delegates persistence to the serializer. This is more than presentation work: it contains deployment-family policy and infrastructure-aware validation.

DeploySerializer.create uses the canonical naming module in deploy.naming and catches database uniqueness races. The database constraint on Deploy is (service, name), so names are reusable across services and unique within a service. This is the correct boundary for the current business rule. API behavior should continue to translate a race into a controlled validation response.

### 3.2 Start and worker ownership

DeployViewSet.start performs additional platform and database checks, changes state, and queues Celery. deployments/celery/tasks.py then dispatches application deployments to DeployService.execute and database deployments to run_db_deploy. The task ID is persisted as the execution owner, and heartbeats plus terminal compare-and-set checks prevent a known stale worker from overwriting a newer owner.

The protection is valuable but distributed. The task wrapper, DeployService, DjangoDeploymentState, monitor recovery, and the legacy service-status layer all participate in ownership or state decisions. The architecture needs one execution context and one transition authority around these existing mechanisms.

### 3.3 Planning and execution

DeployService locks the service with a PostgreSQL advisory lock, materializes a revision when necessary, builds a ServiceRuntimeGraph, normalizes the deployment profile, resolves Plan and operator limits, and flattens the result into DeploymentConfig. DeployFacade performs another translation before constructing DeploymentOrchestrator.

DeploymentOrchestrator.deploy then validates the flattened configuration, extracts the archive, detects/enriches the platform, resolves base images, generates a Dockerfile, builds an image, chooses the Swarm or legacy container path, creates or updates runtime resources, waits for readiness, calls activation, and cleans up or rolls back on failure. It emits events throughout.

This is the critical planning/execution seam. The current DeploymentConfig is effectively a second configuration source after Service, Revision, Plan, and operator settings. It contains user-derived, operator-derived, runtime-derived, build-derived, and compatibility fields with no explicit provenance.

### 3.4 Observation and reconciliation

monitor_services_reconciliation in src/deployments/celery/schedules.py uses Wagtail policies, Redis locks, active deployments, desired service state, stale worker recovery, base-image recovery, and runtime observation. The scheduler directly branches between Swarm and legacy Docker behavior and also requeues or recovers deployment work.

sync_swarm_infrastructure updates SwarmNode observed fields and applies desired availability and labels. SwarmCluster.enabled affects infrastructure synchronization, but the separate process-level SWARM_ENABLED switch controls normal runtime selection. These are different controls with overlapping names and currently inconsistent effect.

## 4. Concrete architectural problems

### 4.1 Three execution paths are still active

The normal application path can execute through Swarm or legacy local Docker. Database deployments use a third specialized implementation. Compatibility is therefore an active alternative architecture, not a thin translation layer. The same concerns—resource handling, health, logs, cleanup, retries, ownership, and state—are implemented or invoked more than once.

Evidence:

- DeploymentOrchestrator branches on swarm_enabled().
- DeployService and Celery tasks branch by platform and runtime.
- DBDeployer contains its own Docker/Swarm deployment behavior.
- ServiceShell and the reconciliation scheduler branch directly between Swarm and legacy containers.

### 4.2 The runtime configuration bag has no ownership model

DeploymentConfig in src/deployments/core/types.py holds image, networks, volumes, environment, process behavior, resource limits, worker counts, build settings, runtime settings, labels, URL behavior, project paths, and base-image values. It is a useful execution DTO but currently also acts as a policy and normalization boundary.

Values are assembled from request input, Service, Plan, ServiceRevision, CoreSettings, SystemSetting, environment, static defaults, and compatibility fields. There is no immutable compiled plan with a source/provenance record. A developer cannot reliably answer why a final runtime value won over another value without following several modules.

### 4.3 DeploymentOrchestrator is a distributed god object

src/deployments/core/orchestrator.py owns validation, archive handling, project inspection, platform enrichment, base-image resolution, Dockerfile generation, image building, runtime selection, network and volume setup, health checks, process containers, activation callback, cleanup, rollback, cancellation and event emission. It directly instantiates Docker managers and SwarmRuntime.

The problem is not the file size alone. Each responsibility has a different source of truth and failure policy. Planning is deterministic and testable; image building is artifact infrastructure; runtime apply is external and idempotency-sensitive; health and rollback require observed state; activation mutates domain state. They should not share one opaque control method.

### 4.4 The API is coupled to infrastructure

DeployViewSet imports and uses SwarmRuntime, DBDeployer, Container, Image, OrchestratorDeploy, and low-level Docker errors. Rebuild and related actions manipulate runtime resources from the view layer. The view also contains config normalization, DB credential checks, state transitions, cancellation semantics, and response construction.

This makes the API a second deployment engine and creates behavior differences between HTTP actions and worker execution. It also makes API tests depend on Docker-specific imports and makes it difficult to provide consistent error conversion.

### 4.5 Configuration is duplicated and precedence is implicit

Deployment behavior can currently come from:

1. process environment and Django startup settings;
2. core.global_settings.config static tables and templates;
3. seeded SystemSetting values;
4. Wagtail CoreSettings values;
5. Plan limits;
6. Service build/runtime/desired-state fields;
7. ServiceRevision snapshots;
8. Deploy.config compatibility/request data;
9. Swarm cluster/node desired state;
10. runtime observation.

There are useful safeguards—tenant config allowlists, operator-owned resource limits, encrypted secret models, and revision snapshots—but the sources are not represented as one explicit resolution graph. Environment fallbacks can silently become policy, and static defaults can remain active after a database setting is introduced.

### 4.6 Swarm is selected by a global process switch

swarm_enabled() in src/deployments/core/swarm.py reads SWARM_ENABLED and defaults to enabled. It is called from the API-adjacent shell path, Celery tasks, scheduler, orchestrator, database deployer, and infrastructure sync. SwarmCluster.enabled is a database field but does not select the runtime for ordinary deployments.

This conflates at least four states:

~~~
operator enabled/disabled
selected backend
Docker daemon reachable/unreachable
cluster active/manager-capable/degraded
~~~

SwarmRuntime.assert_active checks some of these at execution time, but the result is not a first-class capability/availability object used by planning and API validation.

### 4.7 SwarmRuntime is both adapter and policy/compiler

src/deployments/core/swarm.py contains service naming, replica and placement compilation, healthcheck and mount translation, resource conversion, labels, Compose-style service specs, image pushing, network creation, volume pinning, service/task inspection, readiness polling, service creation/update, process graph application, logs, stats, restart, stop, and node synchronization.

The runtime adapter therefore knows about user-facing service graph semantics, operator policy, registry configuration, and Docker SDK details. A future runtime would have to reproduce the whole module or bypass the existing abstractions.

### 4.8 State transitions have an intended authority but multiple writers

core/state/manager.py and common/state_machine.py define an explicit lifecycle and transactional transitions. However, DjangoDeploymentState, DBAndChannelEventSink, monitor actions, Celery entry points, legacy service-status wrappers, and direct queryset updates also mutate or infer deployment state.

There are also duplicate exception definitions in common/state_machine.py. Event sinks infer terminal status from stage/level, which means event naming can become an implicit state machine. Progress updates and terminal transitions need a clear separation.

### 4.9 Application and database strategies do not share a true contract

The database route correctly avoids forcing a database deployment through an application Dockerfile, but it is selected with a separate platform branch and owns much of its own validation, credential, initialization, health, runtime, rollback, and event behavior. Shared lifecycle semantics are conventions rather than a strategy interface.

The architecture should share deployment request, ownership, lifecycle, retry classification, logging, and reconciliation contracts while allowing the application and database planners to produce different runtime plans.

### 4.10 Reconciliation is runtime-aware instead of runtime-independent

The scheduler is the practical recovery mechanism for missed events, stale workers, missing runtime resources, and desired-state drift. It directly knows Swarm and legacy container APIs, Docker labels, runtime names, and recovery details. This makes repeated reconciliation hard to reason about and makes external runtime changes a source of branching behavior rather than observations passed to a policy engine.

### 4.11 Operator control is incomplete and inconsistent

Wagtail already has a good desired/observed pattern for SwarmCluster and SwarmNode: desired availability and labels are editable, observed fields are read-only, and arbitrary node creation/deletion is restricted. It does not yet expose:

- the selected runtime backend;
- runtime capability and availability status;
- cluster-level scheduling, storage, network, image, rollout, or log policy;
- explicit scheduler and log-collector operational state;
- the reason a deployment is blocked by a policy or unavailable capability.

The editable cluster enabled field is also not the same control as the process-level SWARM_ENABLED setting.

### 4.12 Infrastructure assumptions reduce independent testability

The Docker client is a process-wide singleton and eagerly pings on first use. PostgreSQL advisory locks are used for deployment ownership. The deployment log database is a separate alias. These choices can be appropriate in production, but the boundaries are not injected into the application layer, so pure planning and lifecycle tests must isolate or patch infrastructure rather than use clear ports.

The current environment also demonstrates why this matters: Django checks and migration-drift checks can run with the project settings, while full database migration and API integration require PostgreSQL; local Docker runtime checks require a live daemon. The test architecture should make the distinction explicit rather than treating unavailable infrastructure as a hidden dependency of domain tests.

## 5. Configuration ownership map

The table below classifies current ownership and recommends the target owner. “Dynamic” means it can change without rebuilding application code; it does not mean every value should be changed during an active deployment.

| Configuration item | Current source | Target scope/owner | Mutable? | Secret? | Restart? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| Django secret key, allowed hosts, database URLs, Redis/Celery URLs | Environment / Django settings | Environment/process bootstrap | No or controlled rotation | Often yes | Usually yes | Keep outside tenant and deployment policy. |
| SWARM_ENABLED | Environment, default true | Transitional bootstrap selector only | Process-level | No | Yes during migration | Translate once into backend availability; remove scattered reads. |
| Swarm cluster name, registry, namespace | Environment/settings | SwarmCluster plus secret/reference settings | Yes for operator | Registry credentials may be | No for desired state; endpoint clients may refresh | Separate identity, endpoint, registry policy, and credentials. |
| Local volume pinning | Environment and Swarm code | Cluster storage policy | Yes | No | No | Resolve into a placement/storage policy, not a tenant flag. |
| Build mirrors and build resource limits | CoreSettings, SystemSetting, static fallback, env | Platform build policy | Yes | Mirror credentials may be | No | Retain operator ownership and record effective policy in plan provenance. |
| Deployment timeouts, stale-worker and recovery settings | CoreSettings, SystemSetting, static fallback | Platform execution/recovery policy | Yes | No | No | One policy namespace; no duplicate static fallback after migration. |
| Monitor/scheduler settings | CoreSettings, SystemSetting, Celery schedule | Platform subsystem policy | Yes | No | Beat may need refresh | Model enabled, degraded, and unavailable separately. |
| Plan CPU/RAM/worker limits | Plan and resource policy helpers | Platform/tenant plan policy | Yes by operator | No | No | Treat as constraints; service intent cannot exceed them. |
| Service source/build/runtime/desired state | Service | Service domain | Yes | May contain references only | No | Own user intent and non-executable defaults. |
| Process definitions | ServiceProcess | Service domain, snapshotted to revision | Yes | Environment may include refs | No | Validate as intent; do not embed Docker SDK types. |
| Executable image, environment, process graph, endpoints, volumes, networks | ServiceRevision snapshot | Immutable revision | No after creation | Secret values must not be copied | No | Store references/normalized snapshots; create a new revision for changes. |
| One-off deployment request and source artifact | Deploy | Deployment/provenance | Limited before execution | ZIP/config may contain secrets | No | Keep request separate from service desired state. |
| Reusable rollout/retry/health/storage/network policy | Currently split across settings, service, deploy config, and runtime | Platform policy plus optional scoped DeploymentProfile | Yes by operator; snapshot at plan/revision boundary | References only | No | Introduce only where reuse is demonstrated; do not create a generic settings bag. |
| Cluster enabled/backend/scheduling/storage policy | SwarmCluster.enabled plus env and Swarm code | Cluster operator configuration | Yes | Credentials referenced | No | Add explicit desired backend and policy; preserve observed fields separately. |
| Node desired availability/labels | SwarmNode | Node operator intent | Yes | No | No | Existing pattern is appropriate. |
| Node observed availability/labels/capabilities | Docker sync into SwarmNode | Runtime observation | No, runtime-owned | No | No | Never use as desired state. |
| Tenant placement, labels, privileged behavior, host paths, runtime flags | Request/service config plus allowlists | Service intent constrained by platform policy | Limited | Could contain sensitive values | No | Keep only safe declarative intent; platform policy must reject unsafe host authority. |
| Service and deployment secrets | ServiceSecret, env/config snapshots, credentials helpers | Secret store/reference layer | Rotatable | Yes | No | Pass references to planners/adapters; redact at API/event/log boundaries. |
| Runtime service/task status and logs | Docker/Swarm plus log DB | Runtime observation | Runtime-owned | Logs may be sensitive | No | Reconciliation updates observations, not desired state. |

### 5.1 Recommended precedence

The resolution order should be explicit and limited to values for which an override is valid:

~~~
Bootstrap infrastructure
        |
        v
Platform defaults and operator policy
        |
        v
Selected cluster policy and observed capabilities
        |
        v
Service intent and service policy
        |
        v
Immutable revision snapshot
        |
        v
Deployment request overrides allowed by contract
        |
        v
Capability and policy validation
        |
        v
Immutable DeploymentPlan with provenance
~~~

Deployment requests must not override operator-owned resource ceilings, security policy, host paths, cluster selection, or runtime capabilities. A request can choose values explicitly allowed by the service/revision contract; it cannot become host policy.

The compiled plan should retain an explainable map such as:

~~~
replicas = 1
  source: ServiceProcess.replicas
  constrained by: Plan.max_replicas
  runtime check: Swarm.replicas = supported

network = paas-overlay
  source: Cluster.network_policy.default_network
  service override: not permitted
~~~

## 6. Runtime coupling map

The following dependencies should be treated as the first extraction targets:

| Current dependency | Current locations | Why it leaks | Target boundary |
| --- | --- | --- | --- |
| swarm_enabled() | core/swarm.py, API-adjacent actions, tasks, schedules, shell, orchestrator, DB deployer | A process flag selects business behavior in many places | RuntimeRegistry.resolve(selection) once per execution/reconciliation context |
| Docker SDK client | core/swarm.py, manager classes, DB deployer, health checker, log collector | Domain/application code is forced to know Docker availability and exceptions | Runtime adapter and observation ports |
| Docker names/labels | Services models, Swarm runtime, log collector, reconciliation | Identity and observation depend on Docker naming conventions | Runtime identity compiler and adapter-owned labels |
| Swarm service spec compilation | core/swarm.py, core/types.py, orchestrator | User intent and Swarm API shape are mixed | DeploymentPlan followed by Swarm-specific compiler |
| Container readiness | core/health.py and orchestrator | Health policy is tied to local container inspection | Health contract using runtime observation and a runtime health probe |
| Docker image cache/build | Dockerfile generator, image manager, orchestrator, base-image tasks | Artifact lifecycle is coupled to deploy lifecycle | Build/artifact port with explicit leases and provenance |
| Volume/network creation | orchestrator, Swarm runtime, volume manager, DB deployer | Resource policy and runtime calls are interleaved | Resource planner plus runtime resource adapter |
| Logs | DBAndChannelEventSink, legacy event pipeline, Swarm/log collector | Event persistence, WebSocket delivery, Docker logs, and retention overlap | One event contract; separate sinks/adapters |
| PostgreSQL advisory locks | core/state/locks.py, service execution | Lock mechanism is hidden inside domain execution | ExecutionLease port with PostgreSQL implementation |
| Wagtail policy reads | schedules, resource policy, settings helpers | Application execution reaches directly into admin settings | Policy provider resolved in application boundary |

## 7. Proposed architecture

The target is a modular control plane with a narrow runtime contract, not a generic abstraction for every possible backend.

~~~
HTTP / WebSocket / Wagtail
            |
            v
Presentation adapters
            |
            v
Application use cases
  submit / execute / cancel / rollback / reconcile
            |
            +---------------------+
            |                     |
            v                     v
Service and revision       Deployment lifecycle domain
intent                     state, ownership, errors, events
            |                     |
            +----------+----------+
                       v
              Deployment planner
     config resolution + policy + capabilities
                       |
                       v
                 DeploymentPlan
                       |
          +------------+-------------+
          |                          |
          v                          v
 Application strategy          Database strategy
          |                          |
          +------------+-------------+
                       v
                 Runtime contract
                       |
          +------------+-------------+
          |                          |
          v                          v
    Swarm adapter              Future adapter
          |
          v
 Docker/Swarm observed state
          |
          v
 Runtime observation + reconciliation
~~~

An illustrative package shape is:

~~~
deployments/
  application/       # use cases and execution context
  domain/            # lifecycle, errors, events, immutable plan types
  planning/          # config resolver, policies, capability checks
  strategies/        # application and database plan/execution strategies
  runtime/           # contract, registry, observations, capabilities
    swarm/           # Swarm compiler and adapter
  build/             # source inspection, Dockerfile, artifact/image ports
  reconciliation/    # desired/observed convergence policies
  infrastructure/    # Celery, PostgreSQL lease, Docker implementations
~~~

The names are illustrative. Existing modules may remain where they are during migration. The important boundary is dependency direction: domain and planning must not import Docker SDK objects, Wagtail settings, or Celery request objects.

### 7.1 Deployment plan

DeploymentPlan should be the compiled, validated output of service intent, revision, profile/policy, cluster policy, and runtime capability checks. It should contain normalized values needed by an adapter:

~~~
service/revision/deployment identity
runtime selection and cluster identity
process graph
image/artifact reference
environment references
secret references
networks and volumes
endpoints
resource limits
placement constraints permitted by policy
health/readiness policy
rollout and retry policy
logging policy
provenance/explain map
~~~

It must not contain a live Docker service object, a Celery request, a Django model instance required for execution, or raw tenant host-policy directives.

ServiceRuntimeGraph is the existing closest fit for the process/resource portion of this plan and should be reused rather than replaced. DeploymentConfig should become a compatibility input or be reduced to an adapter-specific build request after the plan boundary exists.

### 7.2 Runtime contract

The first contract only needs operations required by current behavior:

~~~
describe_capabilities() -> RuntimeCapabilities
check_availability() -> RuntimeAvailability
apply(plan, operation_key) -> RuntimeHandle
wait_ready(handle, health_policy, cancellation) -> ReadinessResult
inspect(identity) -> ObservedRuntime
stop(handle, operation_key)
remove(handle, operation_key)
rollback(plan or runtime handle, operation_key)
logs(identity, cursor/policy)
~~~

The contract must define idempotency keys, ownership of resource names, retryable versus terminal errors, and the distinction between not found, unavailable, unsupported, and failed. The domain sees typed observations and errors, not Docker SDK exceptions.

### 7.3 Capabilities and availability

Use structured capabilities rather than unrelated booleans:

~~~
RuntimeCapabilities:
  service_scheduling
  replicas
  rolling_update
  rollback
  node_constraints
  overlay_networks
  persistent_volumes
  service_logs
  health_checks
  process_graph

RuntimeAvailability:
  operator_enabled
  reachable
  backend_active
  manager_capable
  cluster_health
  last_checked
  reason/code
~~~

Capabilities describe what a backend can do. Availability describes whether it can do it now. A plan is rejected before side effects when a required capability is unsupported; it is blocked or retried when the capability exists but the runtime is unavailable.

### 7.4 Runtime selection

Runtime selection should occur at one application boundary from service/profile/cluster policy, with an explicit result:

~~~
RuntimeSelection:
  backend = swarm
  cluster = primary
  reason = service profile -> cluster default
  required_capabilities = {service_scheduling, health_checks}
~~~

The application layer should never instantiate SwarmRuntime directly. The registry can initially contain only Swarm, with the existing legacy Docker behavior represented as an explicitly selected compatibility backend during migration—not as an implicit fallback whenever a global flag is false.

## 8. Configuration model and deployment profiles

### 8.1 Bounded configuration objects

The target should use bounded configuration records rather than a universal configuration JSON:

~~~
PlatformPolicy
  build, security, resource ceilings, retry defaults, log retention

ClusterPolicy
  backend, enabled state, scheduling, networks, storage, registry, rollout defaults

NodeIntent
  desired availability and labels

ServiceIntent
  source, process graph, endpoints, desired state, service-level policy

RevisionSnapshot
  immutable executable image/source/configuration and references

DeploymentRequest
  revision selection, actor, idempotency key, permitted request overrides

RuntimePlan
  final normalized adapter input plus provenance
~~~

Not every item requires a new Django model. Existing Service, ServiceRevision, SwarmCluster, SwarmNode, Plan, and Wagtail settings should be reused where ownership already matches. A dedicated reusable DeploymentProfile is justified only if operators need the same policy assigned to multiple services and the profile has a stable lifecycle. Otherwise, a normalized policy snapshot at revision/deployment planning time is less indirection.

### 8.2 Configuration source rules

- Environment variables remain for process bootstrap, connection endpoints, credentials, and emergency startup gates.
- Wagtail/database settings own operator policy that should be changed without rebuilding the control plane.
- Cluster and node models own scoped runtime intent and observed facts.
- Service owns tenant/service intent.
- Revision owns immutable executable configuration.
- Deploy owns a request and provenance, not a mutable replacement service definition.
- Runtime owns observations and operation handles.
- Secrets remain references at planning boundaries and values are resolved only by an authorized infrastructure adapter.

SystemSetting can remain as a migration-compatible store for scalar operator settings, but new deployment policy should not expand an untyped global key/value namespace without a category, scope, validation schema, and audit trail.

## 9. Wagtail operator control plane

The existing desired/observed SwarmCluster and SwarmNode pattern should be extended rather than bypassed.

### Operator-managed desired state

- selected backend and cluster enabled/maintenance mode;
- scheduling and placement policy;
- image registry/namespace reference;
- default network and storage policy;
- rollout, health, retry, cleanup, and log retention policy;
- node availability and safe labels;
- scheduler/log collector desired mode.

### Runtime-observed state

- Docker reachability and Swarm manager capability;
- cluster active/degraded state;
- node observed availability and labels;
- runtime service/task counts and versions;
- last synchronization/error/capability check;
- log collector heartbeat and ingestion health.

Observed values must remain read-only in Wagtail. Operator actions update desired values and enqueue reconciliation. Wagtail must not claim that a desired drain or backend enablement is already effective.

Secrets, raw Docker sockets, arbitrary host paths, and unrestricted placement constraints must not become editable tenant or Wagtail JSON fields.

## 10. Safe enable/disable semantics

The behavior should be explicit and visible in API/admin status.

| Subsystem state change | Existing work | New work | Reconciliation | Operator/API result |
| --- | --- | --- | --- | --- |
| Swarm backend disabled | Do not stop or delete running services | Reject new plans targeting Swarm with runtime_disabled; allow an explicitly configured fallback only | Inspect-only for existing Swarm resources, no destructive convergence | blocked/maintenance with reason and last observed state |
| Docker/Swarm unreachable | Running workloads remain untouched | Queue or fail according to retry policy; do not pretend a plan was applied | Record degraded availability and retry safely | Structured runtime_unavailable, not a raw SDK error |
| Cluster not manager-capable | No destructive action | Reject operations requiring manager writes | Continue safe observation if possible | Capability-specific error |
| Scheduler disabled | In-flight worker may finish under lease | No new scheduled executions; manual action behavior explicit | Pause automatic repair, retain desired/observed drift | Admin shows paused, not healthy |
| Log collector disabled | Historical logs remain | No new collector ingestion | Runtime-native logs may remain available | Observability degraded; no false logs-complete state |
| Node maintenance/drain desired | Existing service movement follows policy | New placement honors desired state | Apply desired availability and report convergence | Desired and observed values shown separately |

Disabling a backend must not silently switch every service to a legacy runtime. Fallback must be a deliberate runtime policy on the service/profile or an operator-approved maintenance mode.

## 11. Orchestrator responsibility map

The current orchestrator should be decomposed by behavior, not line count:

| Responsibility | Target component | Input/output |
| --- | --- | --- |
| Resolve service/revision/policies/capabilities | Planner | Domain inputs -> immutable DeploymentPlan or typed rejection |
| Inspect source and build artifact | Build service | Source/revision -> artifact/image reference |
| Translate plan to backend spec | Swarm compiler | DeploymentPlan -> Swarm-specific request |
| Apply/update runtime | Runtime adapter | Backend request -> runtime handle/operation result |
| Readiness and health | Health service + runtime observation | Handle + health policy -> readiness result |
| Activate revision | Service lifecycle application service | successful readiness + ownership -> active revision transition |
| Roll back | Rollback policy/application service | previous known-good plan/handle -> convergence result |
| Cleanup | Resource ownership service | operation/resource ledger -> idempotent cleanup |
| Emit/persist events | Event publisher/sinks | typed lifecycle event -> log DB, channels, structured logs |
| Retry/cancel | Execution application service | typed failure/cancellation -> one lifecycle decision |

The orchestrator can remain as a temporary façade that delegates to these components. Removing it first would increase migration risk.

## 12. Application and database strategies

Use one shared lifecycle contract:

~~~
DeploymentRequest
    -> StrategyResolver
    -> DeploymentStrategy.plan(context)
    -> DeploymentPlan
    -> common executor (ownership, cancellation, retry, events, terminal state)
    -> runtime adapter
~~~

ApplicationStrategy may invoke source inspection and image building. DatabaseStrategy may resolve a managed/external image, initialize credentials, and express database-specific readiness. Both must use the same execution context, state machine, fencing, event schema, and reconciliation interface. They must not share an application Dockerfile pipeline merely to appear uniform.

## 13. Desired-state reconciliation design

Reconciliation should consume three explicit inputs:

~~~
DesiredState: Service + active revision + policy
ObservedState: RuntimeObservation from adapter
Provenance: Deploy/operation records and ownership leases
~~~

It should produce an idempotent ReconciliationAction:

~~~
converged
apply_create
apply_update
stop
adopt (only under explicit policy)
block_unavailable
repair_orphan
manual_intervention_required
~~~

Examples:

- Desired running, observed missing: create/apply the active revision if the backend is enabled and capable.
- Desired stopped, observed running: stop only resources owned by the service and according to lifecycle policy.
- Desired revision B, observed revision A: plan an update/rollout from B; do not mutate B into A or treat the old Deploy row as current runtime truth.
- Observed resource externally deleted during an in-flight deployment: the owner/fence and operation key determine whether to retry, repair, or mark the operation failed.

The reconciler must not use an event as the sole source of truth, must not create a destructive loop when the backend is unavailable, and must be safe to run repeatedly.

## 14. Observability and security implications

Every lifecycle event and runtime operation should carry, where available:

~~~
service_id
revision_id
deployment_id
worker_task_id
operation_key
runtime_backend
cluster_id
runtime_service_id/name
stage
error_code
recoverable
correlation_id
~~~

DBAndChannelEventSink and the legacy DeploymentEventPipeline currently overlap. They both persist/broadcast events, but sanitization is implemented more clearly in the legacy pipeline than in the sink path. The event contract should have one redaction boundary before any persistence, logging, or WebSocket delivery. A structured event must never include secret values, credentials embedded in configuration, or full private keys.

The runtime adapter should also be the only layer that translates a secret reference into a Docker secret/environment mount. Plans, APIs, event details, and log records should retain references or redacted metadata.

## 15. Migration strategy

Migration should preserve existing data and keep the branch isolated.

1. Characterize current behavior. Add tests around current service/revision/deploy lifecycle, name scope, ownership fencing, cancellation, rollback, API errors, and current Swarm naming before changing execution.
2. Introduce ports without changing behavior. Define runtime capabilities, availability, observations, and operation errors. Wrap the existing SwarmRuntime behind the contract; do not rewrite Swarm calls yet.
3. Create one configuration resolver. Read existing sources with an explicit precedence order and emit a provenance-bearing normalized policy. Keep compatibility reads but stop adding new direct settings reads.
4. Compile a plan. Build DeploymentPlan from the current ServiceRuntimeGraph, revision, Plan, policy, and runtime capabilities. Keep a temporary adapter from the plan to DeploymentConfig.
5. Move execution decisions to one use case. Have HTTP actions call application services for start, cancel, rollback, rebuild, and reconcile. Leave response serializers in the presentation layer.
6. Add strategy resolution. Route application and database deployments through a common lifecycle executor with specialized planners. Preserve database-specific image/init behavior.
7. Move reconciliation behind observations. Make the scheduler ask the selected runtime for observations and apply typed actions; isolate legacy container observation as a compatibility adapter.
8. Make operator controls authoritative. Reconcile SwarmCluster desired backend/policy and SwarmNode desired fields. Persist availability and capability results. Translate SWARM_ENABLED only as a bootstrap compatibility input.
9. Isolate legacy runtime. Require explicit compatibility selection; stop using swarm_enabled() as a distributed branch. Remove legacy code only after parity and migration coverage.
10. Retire duplicate paths. Consolidate event sinks, state mutation, config parsers, error types, and runtime cleanup after evidence shows no remaining callers.

Existing selected_deploy and deployment rows remain compatibility projections. No data migration should rewrite historical Deploy provenance merely to fit the new model. New revisions remain immutable, and active revision changes remain explicit.

## 16. Test strategy and current evidence gaps

### Fast/domain tests

- policy precedence and provenance;
- capability mismatch versus runtime unavailable;
- immutable revision snapshots;
- deployment state transition validity;
- ownership lease and stale-worker fencing;
- cancellation versus completion race;
- idempotency keys and repeated plan/application;
- retry classification;
- secret redaction;
- tenant policy cannot set operator-owned host policy.

### Application/API tests

- real DRF create/start/cancel/rollback/reconcile paths;
- service-scoped deployment names and uniqueness races;
- shared-service authorization;
- structured validation/runtime errors;
- pagination, filters, status, logs and redaction;
- application and database strategy selection;
- Wagtail desired versus observed updates.

### Runtime contract tests

Run the same contract suite against a fake runtime and the Swarm adapter:

- create/update/repeat apply;
- readiness and health failure;
- external deletion and task movement;
- stop/rollback/retry;
- logs and observations;
- unavailable backend and unsupported capability.

### Integration/runtime tests

- PostgreSQL migration and cross-database DeployLog behavior;
- Celery task execution and worker replacement;
- Docker/Swarm service/task readiness, network, volume, image, and rollback behavior;
- reconciliation after externally deleting or modifying runtime resources;
- operator disable/maintenance scenarios.

The existing focused lifecycle/security tests provide useful coverage, but they do not prove the runtime abstraction or the real API/database/Swarm path. Local verification has also shown that project checks can run while PostgreSQL and Docker are unavailable. Those environment constraints must be reported separately from repository failures; they must not be hidden by weakening tests.

## 17. Migration risks

1. Existing revision and active-deploy data. ServiceRevision, active_revision, and selected_deploy must continue to resolve the same historical intent.
2. Swarm naming and labels. Runtime identity changes can orphan or duplicate services; the adapter must preserve names and label compatibility during migration.
3. Volumes and placement. Local-volume pinning and node constraints are operationally significant and cannot be reduced to generic fields without a migration plan.
4. Database credentials and initialization. Database strategies have different idempotency and readiness semantics from application builds.
5. Legacy mode. Removing implicit fallback too early could strand existing local-container deployments; retaining an unbounded second path would preserve the current problem.
6. State writers. Moving terminal transitions away from event sinks and monitor actions can expose hidden assumptions in WebSocket/UI progress behavior.
7. Operator semantics. Splitting process bootstrap flags from Wagtail desired state can create contradictory controls unless the effective state is displayed.
8. Runtime availability. A plan can be valid while its backend is unavailable; API and scheduler behavior must distinguish blocked, retrying, failed, and converged.
9. Separate log database. Event persistence must remain best-effort without allowing failures to corrupt deployment state or leak secrets.
10. Multi-node Swarm behavior. Local tests cannot prove scheduling, image distribution, health, endpoint, or volume behavior; real Swarm verification remains a release gate.

## 18. Phased implementation plan

### Phase 0 — characterization and contract decisions

- Freeze the report and agree the ownership/precedence rules.
- Add missing characterization tests for API, state, naming, revision immutability, and current Swarm naming.
- Define typed errors, runtime availability, capabilities, observations, and idempotency keys.

### Phase 1 — configuration boundary

- Implement one resolver over existing sources.
- Return normalized policy plus provenance.
- Keep environment values limited to bootstrap and compatibility.
- Add invalid/disabled/unavailable configuration tests.

### Phase 2 — runtime contract and Swarm adapter

- Wrap existing SwarmRuntime behind the contract.
- Separate capability/availability checks from apply operations.
- Add fake-runtime contract tests and preserve current names/labels.

### Phase 3 — deployment planning

- Compile Service + Revision + policy + cluster + capabilities into DeploymentPlan.
- Keep ServiceRuntimeGraph as the domain graph source.
- Adapt the current orchestrator through a temporary plan-to-config bridge.

### Phase 4 — common lifecycle executor and strategies

- Centralize ownership, transitions, cancellation, retry classification, activation, rollback, and terminal events.
- Add application and database strategy planners.
- Remove duplicated lifecycle decisions from the view and task wrappers.

### Phase 5 — API and operator controls

- Move runtime actions behind use cases.
- Standardize structured errors.
- Extend Wagtail desired/observed controls and show runtime availability/capabilities.
- Define deterministic enable/disable behavior in API and admin.

### Phase 6 — reconciliation and observability

- Make adapters provide observations.
- Compile typed reconciliation actions.
- Consolidate event sinks and redaction.
- Test missed events, external deletion, task movement, and repeated repair.

### Phase 7 — compatibility isolation and cleanup

- Make legacy local Docker an explicit backend.
- Remove scattered swarm_enabled() branches and dead imports.
- Retire duplicated parsers, state writers, error definitions, and runtime paths only after parity tests.

### Phase 8 — real runtime validation

- Validate PostgreSQL migrations and cross-database logs.
- Run full API/Celery integration.
- Exercise real Swarm service/task/image/network/volume/health/log/reconciliation behavior.
- Review the full diff against current master; keep the branch isolated if any release criterion remains uncertain.

## 19. Acceptance criteria for the redesign

The architecture work is ready for implementation review when:

- one documented resolver explains each effective deployment value;
- one runtime-selection point returns backend, cluster, capability requirements, and availability;
- domain/planning code imports no Docker SDK or Celery request types;
- application and database deployments share lifecycle/ownership/event contracts but retain specialized planners;
- one authoritative lifecycle transition mechanism exists;
- repeated apply, reconcile, cleanup, and activation are idempotent;
- Wagtail displays desired versus observed operator/runtime state;
- disabling a subsystem has documented, tested semantics;
- selected_deploy remains only a compatibility projection;
- Swarm behavior is exercised through the runtime contract, not assumed by Compose tests;
- the report's migration risks have corresponding tests or explicit operational controls.

## 20. Decision summary

The repository does not need another global settings file or a large speculative backend framework. It needs:

1. explicit configuration ownership and precedence;
2. one compiled deployment plan;
3. one runtime contract with capabilities and availability;
4. specialized application/database strategies under one lifecycle executor;
5. one state/ownership authority;
6. desired/observed reconciliation behind runtime adapters;
7. Wagtail controls that express operator intent without pretending to own Docker observations;
8. a staged migration that preserves current service/revision/deployment data and Swarm identities.

This report is the first deliverable. The next phase should begin with characterization tests and contract definitions, not a wholesale rewrite of DeploymentOrchestrator, SwarmRuntime, or DBDeployer.

## 21. Implementation status on `refactor/service-centric-runtime`

The first incremental implementation slices now exist and are intentionally
compatible with the current runtime rather than pretending that the migration
is complete:

- characterization tests cover the current runtime graph and Swarm
  configuration identity;
- `deployments.runtime` defines backend identity, capabilities, availability,
  observations, typed runtime errors, a fake runtime, a registry, and a
  Swarm adapter around the existing runtime implementation;
- `deployments.planning` resolves scoped configuration with provenance and
  compiles a capability-checked `DeploymentPlan`;
- a compatibility compiler translates a plan into the existing
  `DeploymentConfig`, preserving current Swarm names, labels, resources, and
  explicit health checks;
- the revision-backed Swarm path now compiles that compatibility plan before
  invoking the existing facade;
- `deployments.application` provides a pure, fenced lifecycle executor with
  ownership checks, cancellation, retry classification, rollback hooks, and
  terminal idempotency;
- the application layer now has one strategy-resolution seam for application
  and database workloads, so specialized planners can share the lifecycle
  contract without routing database deployments through an application build
  pipeline;
- `deployments.reconciliation` provides a pure desired-versus-observed
  decision planner.

The following are still transitional and are not claimed as complete:

- the Celery worker still owns the surrounding orchestration and has not yet
  been fully migrated to the lifecycle executor;
- the Django state manager, event sinks, API actions, Wagtail controls, and
  database/application strategy selection are not yet unified behind the new
  ports;
- runtime observations are not yet the active reconciliation input for every
  deployment path;
- legacy local-Docker behavior remains compatibility behavior and is not yet
  an explicit, fully isolated backend;
- PostgreSQL, Docker/Swarm, Wagtail, and full-suite verification remain
  environment-sensitive release work.

This status is part of the design contract: new code must extend the seams
above or explicitly document why an existing compatibility path remains. It
must not introduce another direct Docker path or another independent
deployment state machine.

