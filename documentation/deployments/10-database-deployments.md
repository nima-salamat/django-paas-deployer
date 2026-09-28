# 10 — Database deployments

## Purpose

Database deployment is a specialized execution branch inside the common deployment architecture.

It shares lifecycle concepts such as Deploy ownership, Service locking, revision/provenance, event logging and terminal state, but deliberately does not use the application source-to-Dockerfile build pipeline.

## Branch point

~~~text
common request / Deploy
       |
       v
Celery task
       |
       +--------------------+
       |                    |
application              database
       |                    |
platform/build          DBDeployer
       |                    |
       v                    v
application image       engine image/init
       |                    |
       +---------+----------+
                 |
              runtime/readiness
                 |
             terminal state
~~~

The branch exists because a database server is not an application source artifact.

## How routing works

**Entry:** \`deployments.celery.tasks.deploy()\`

The task inspects the requested/planned platform.

If it belongs to \`DB_PLATFORMS\`, the task redirects to \`run_db_deploy\`.

**Database task:** \`deployments.celery.tasks.run_db_deploy()\`

It acquires the Service deployment lock and calls \`DBDeployer.deploy()\`.

## Common lifecycle before specialization

### Preconditions

- Deploy exists;
- Service exists;
- database platform is supported;
- Service deployment ownership is acquired.

### Shared state

The database task participates in the same Deploy lifecycle and revision/provenance model.

### Specialized boundary

After ownership/revision validation, database-specific code owns engine configuration, initialization and readiness.

## DBDeployer

**Path:** \`deployments/core/db_deployer.py\`

### Owns

- fixed database engine image selection;
- engine-specific environment;
- initialization behavior;
- persistent-volume use;
- credentials/database reconciliation;
- database-specific readiness;
- database runtime error classification.

### Does not own

- application platform detection;
- application Dockerfile generation;
- arbitrary tenant Docker infrastructure policy.

## Supported engines

Current \`DB_PLATFORMS\`:

- mysql;
- mariadb;
- postgresql;
- mongodb;
- redis;
- oracle.

Fixed images are defined in \`core/db_deployer.py\`.

## Validation

\`validate_db_config()\` checks engine-specific rules before Docker mutation.

Examples:

- MySQL/MariaDB require root password;
- PostgreSQL requires password;
- MongoDB requires username/password;
- Oracle requires password;
- port must be 1..65535;
- application username must not be root for MySQL/MariaDB.

Sensitive values are not intentionally exposed in ordinary logs.

## Why database readiness is specialized

Official database images may start a temporary initialization server.

Therefore:

~~~text
container running
       |
       !=
database accepting real credentials
~~~

For MySQL/MariaDB the readiness path requires:

1. official initialization completed;
2. temporary server stopped;
3. final mysqld running;
4. authenticated mysqladmin ping succeeds.

Only then does credential/database reconciliation run.

## Persistent volumes

Database state is durable infrastructure.

Normal redeployment should reuse the existing volume.

Changing initialization environment variables does not rewrite an already initialized database directory.

Therefore normal MySQL/MariaDB redeployment performs explicit credential reconciliation after readiness.

## force_reinit

\`run_db_deploy(force_reinit=True)\` is explicit destructive behavior.

It can wipe named DB volumes so the official engine image initializes from scratch.

### Preconditions

Operator/client explicitly requested reinitialization.

### Effect

All data in affected DB volumes may be lost.

### Must not

Never infer \`force_reinit\` from a normal deployment retry or failure.

## Locking and duplicate delivery

Database deployment uses the same Service advisory lock as application deployment.

This protects against:

- duplicate Celery delivery;
- overlapping API/admin actions;
- monitor/retry races.

A duplicate task should exit or be prevented by the state gate rather than mutating the same database concurrently.

## Retry semantics

DB task retries are bounded.

The retryability predicate distinguishes transient Docker/API/network/timeouts from deterministic validation/programming failures.

### Why

Repeating SQL initialization against a persistent database is not equivalent to repeating a stateless image build.

Retry behavior must preserve data safety.

## Runtime integration

The DB deployer can use the common Swarm runtime for:

- managed service lifecycle;
- network;
- volume placement;
- runtime observation.

The database-specific layer still owns engine semantics.

This is a specialization, not a copy of the whole deployment engine.

## Revision/provenance

Database Deploy rows still participate in revision creation.

That preserves a stable history of what database configuration/access binding was deployed even though the image itself comes from a fixed engine image.

## Error flow

~~~text
validation error
   -> terminal failure

runtime/init transient
   -> bounded retry where classified recoverable

persistent/credential error
   -> deployment failure with DB diagnostics

force-reinit failure
   -> failure with explicit destructive-operation context
~~~

## How to change database behavior

| Desired change | Start here | Avoid changing |
|---|---|---|
| engine image/version | \`core/db_deployer.py\` | application Dockerfile |
| DB readiness | \`core/db_deployer.py\` | generic app health assumptions |
| database password reconciliation | DB-specific SQL helpers | global config parser |
| DB routing | \`celery/tasks.py\` | platform plugin detection |
| DB runtime placement | Swarm runtime | engine credential logic |
| DB state transition | StateManager/task failure path | direct status assignment |

## What database deployment must NOT do

Do not:

- send database workloads through application Dockerfile generation;
- silently wipe persistent volumes;
- treat “container running” as database readiness;
- expose passwords in logs;
- bypass Service locking;
- bypass the shared lifecycle state contract.

## Related code

- \`src/deployments/celery/tasks.py::run_db_deploy\`
- \`src/deployments/core/db_deployer.py\`
- \`src/deployments/core/swarm.py\`
- \`src/services/revisioning.py\`
- \`src/deployments/core/state/locks.py\`
- \`src/deployments/common/state_machine.py\`
- \`documentation/domain/databases-storage.md\`
