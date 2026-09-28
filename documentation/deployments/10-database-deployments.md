# 10 — Database deployments

## Purpose

Database workloads share the deployment domain but intentionally diverge from the application ZIP/build pipeline.

## Database platforms

The current DBDeployer supports:

- mysql;
- mariadb;
- postgresql;
- mongodb;
- redis;
- oracle.

## Routing

deployments.celery.tasks.deploy determines whether the workload is a database platform and routes it to run_db_deploy.

run_db_deploy performs the database-specific execution through deployments.core.db_deployer.DBDeployer.

This prevents database workloads from being sent through the application Dockerfile/build path.

## Shared lifecycle, specialized execution

The shared model remains:

~~~text
Deploy
  -> ownership
  -> revision/provenance
  -> validation
  -> runtime operation
  -> readiness
  -> terminal state
~~~

The intentional difference is the execution core between validation and readiness.

Application deployments inspect source and build an application image.

Database deployments use engine-specific images and initialization/credential reconciliation.

## Validation

validate_db_config() enforces engine-specific rules.

Examples:

- MySQL/MariaDB require a root password;
- PostgreSQL requires a password;
- MongoDB requires username and password;
- Oracle requires a password;
- ports must be between 1 and 65535;
- MySQL/MariaDB do not allow root as the application username.

Sensitive values are excluded from ordinary diagnostics.

## Database images

The current fixed engine images in core/db_deployer.py are:

| Engine | Image |
| --- | --- |
| MySQL | mysql:8.0.36 |
| MariaDB | mariadb:11 |
| PostgreSQL | postgres:16-alpine |
| MongoDB | mongo:7 |
| Redis | redis:7-alpine |
| Oracle | gvenzl/oracle-xe:21-slim |

These are implementation policy for the database deployment path. They are not the tenant-controlled application image contract.

## Initialization versus readiness

Database containers often have an initialization period during which the container is running but the service is not ready.

MySQL/MariaDB therefore use an explicit readiness sequence:

1. official entrypoint initialization completes;
2. temporary initialization server stops;
3. final mysqld remains running;
4. authenticated mysqladmin ping succeeds.

The database deployer then performs credential/database reconciliation.

Do not replace this with a generic “container is running” check.

## Persistent-volume behavior

Database data is stored in persistent volumes.

Changing initialization environment variables does not retroactively modify an already initialized data directory.

This is why normal redeployment against an existing MySQL/MariaDB volume performs explicit SQL credential/database reconciliation after readiness.

## MySQL/MariaDB credential reconciliation

The deployer:

1. starts the database;
2. waits for the final server to be ready;
3. connects through the local Unix socket;
4. reconciles root credentials;
5. creates or updates the application user;
6. creates the requested database;
7. grants database access;
8. verifies the credentials.

Passwords are not logged.

## force_reinit

force_reinit=True is explicit destructive behavior.

The task can wipe attached database volumes so the official image initializes from scratch.

A normal deployment must not infer or enable this flag.

## Locking and retries

run_db_deploy uses the same per-Service PostgreSQL advisory lock as application deployment.

It also has a strict state/queue gate so duplicate deliveries do not start overlapping database mutations.

Database retries are bounded and depend on the unified retryability classification.

Deterministic validation/configuration failures are not blindly retried.

## Runtime integration

Database resources may be executed through the common Swarm runtime for managed service lifecycle, networking, volumes, placement and observations.

DBDeployer itself owns the database-specific:

- engine image;
- environment;
- initialization;
- credential reconciliation;
- readiness logic.

It should not duplicate application platform detection or Dockerfile generation.

## Revision relationship

Database Deploy rows still participate in the revision/provenance architecture through ensure_revision_for_deploy().

That preserves execution history and immutable service snapshots even though the database image is not generated from application source.

## What database deployment must NOT do

Do not:

- call the application Dockerfile generator for database engines;
- treat initialized persistent databases as fresh containers;
- silently wipe persistent volumes;
- expose root/application passwords in logs;
- bypass Service deployment locking;
- bypass the lifecycle state machine.

## Related code

- src/deployments/celery/tasks.py::run_db_deploy
- src/deployments/core/db_deployer.py
- src/deployments/core/swarm.py
- src/services/revisioning.py
- src/deployments/core/state/locks.py
- documentation/domain/databases-storage.md
