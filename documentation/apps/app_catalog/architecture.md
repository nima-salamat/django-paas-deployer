# Ready-to-Deploy Application Architecture

## 1. Boundary

`app_catalog` is the catalog compiler and installation coordinator.

It performs catalog parsing/security validation, variant resolution, immutable installation-intent capture, child Service/Deploy materialization, and application-level dependency scheduling/cancellation/timeout/reconciliation.

It does not execute Docker, build images, perform readiness checks, or implement a second deployment runtime.

## 2. Responsibilities

| Concern | Authority |
|---|---|
| Catalog template | catalog source |
| Installed identity | ApplicationInstance |
| Installed orchestration graph | ApplicationInstance.definition_snapshot |
| Child mapping | ApplicationInstanceService |
| Mutable desired service configuration | Service / ServiceRevision |
| Deployment attempt | Deploy |
| Build/runtime/readiness execution | deployments |
| Durable secret value | ServiceSecret / ServiceSecretVersion |
| Runtime observation | deployments/runtime |
| Docker resources | deployments/runtime |
| Application coordinator state | ApplicationInstance |
| Child deployment state | Deploy |

## 3. Non-responsibilities

The catalog coordinator never becomes a deployment engine, secret store, Service state machine, revision store, or Docker resource manager.

`ServiceProcess(name="web")` is retained as a runtime compatibility name. Its `process_type` carries the actual role, such as `database`, `worker`, or `scheduler`.

## 4. Data flow

```text
Catalog Definition
    -> resolve_variant / Compose adapter
    -> ApplicationPlan
    -> immutable ApplicationInstance intent
    -> ApplicationInstanceService
    -> Service + Deploy
    -> ServiceRevision
    -> deployments
    -> Docker / Swarm
```

## 5. Source of truth

`ApplicationInstance.definition_snapshot._application_orchestration.services` is the coordinator's immutable graph. It contains service key, role, platform, plan type, dependencies and required/optional status.

`Service.runtime_config` is mutable desired runtime configuration. It must never be used to rewrite the coordinator graph.

Recovery therefore never reloads the current catalog and never regenerates catalog secrets.

## 6. Installation snapshot

The snapshot is written at installation creation and protected by the ApplicationInstance model. Catalog identity fields and the snapshot cannot be changed after creation.

A migration backfills the orchestration graph for older installations from persisted child materialization. New installations always contain the graph before child bindings are created.

## 7. Secret lifecycle

Catalog resolution preserves `${secret.name}` references. Secret values remain in the private resolved compiler result only until the service materializer reaches the secret-aware boundary.

Only referenced secrets are materialized for a child Service. Exact secret environment values become ServiceEnvironmentVariable.secret references. Composite expressions become a dedicated encrypted ServiceSecret with an empty plaintext environment value.

Catalog secrets are rejected in Dockerfiles/build files and other unsupported build locations. DB credentials are persisted as secret references in Deploy/Service revision input and are materialized by the normal revision compiler.

## 8. Child Service lifecycle

A catalog child is a normal Service with `source_kind=catalog`. Its desired configuration still flows through the normal ServiceRevision -> Deploy pipeline.

Its execution ownership is not independently transferable: plan, network and catalog provenance cannot be changed through normal Service mutation while the application binding exists. Child deletion is rejected and must occur through ApplicationInstance deletion.

## 9. Database child model

A catalog database child is a first-class Service using a Plan with `plan_type=DB` and the declared database platform, followed by a normal Deploy. `deployments.celery.tasks.run_db_deploy` routes it to the existing `DBDeployer`.

`DatabaseResource` / `ServiceDatabaseBinding` remains the repository abstraction for managed database resources exposed to workload services. Catalog-installed database children do not masquerade as APP plans and do not create a duplicate database subsystem.

## 10. DAG scheduling

`ApplicationInstanceService.sequence` is deterministic presentation/materialization order only.

`depends_on` is the execution constraint. `ready_service_keys()` returns the parallel execution frontier.

A required service may not depend on an optional service. Optional dependency failure blocks and terminalizes downstream optional nodes; a required failure fails the application and terminalizes undispatched siblings.

The application becomes RUNNING only after all child Deploys are terminal and every required child succeeded.

## 11. Failure, cancellation and timeout

A required child failure transitions the application to FAILED, cancels pending siblings and requests cancellation of running/rolling-back siblings.

Cancellation is durable through `cancel_requested`. Pending children are terminalized; active Deploys receive cancellation intent and are left to the normal deployment engine to converge.

The application deadline is owned by ApplicationInstance. Deadline expiry uses the same cancellation convergence path and remains distinguishable by `APPLICATION_DEPLOYMENT_TIMEOUT`.

## 12. Recovery

Coordinator task ownership uses `execution_task_id` and per-child `dispatch_task_id`. A stale gate callback cannot execute after its claim has been replaced.

Reconciliation may clear a stale pending dispatch claim and retry it. It never re-resolves the catalog or regenerates secrets.

## 13. Deletion

Application deletion requires a terminal ApplicationInstance and no active child Deploys. Child bindings prevent direct child deletion, while compound User deletion is allowed to remove the installation graph together with its owned children. Catalog Deploy archives are explicitly removed from storage.

Direct child Service deletion is rejected while an ApplicationInstanceService binding exists. Direct binding targets are restricted by the database.

## 14. Concurrency and fencing

The `(user, slug)` uniqueness constraint is the final installation identity guard. Only its specific uniqueness violation is translated to the application-name conflict response.

Coordinator callbacks are fenced by their dispatch token. Deploy execution remains fenced by the Deploy/deployment engine.

## 15. API boundary

Catalog APIs enforce authenticated owner isolation. Installation creation returns 202 after durable creation and queueing; broker failure leaves a pending installation for reconciliation. Terminal application deletion is explicit and coordinated rather than delegated to generic Service deletion.