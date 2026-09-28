# Database Deployments

Managed database services share the common Service -> ServiceRevision -> Deploy -> deployments lifecycle but retain specialized engine setup/readiness.

## Database domain

Database resources/bindings/credentials are owned by [apps/services/](../apps/services/README.md). Deploy records and database API controls are owned by [apps/deploy/](../apps/deploy/README.md).

## Execution

deployments.celery.tasks.run_db_deploy and deployments/core/db_deployer.py own the specialized database execution behavior. The common lifecycle/ownership contract remains in deployments/ and Service revisioning.

## Runtime

Managed database engines run through the runtime architecture documented in 05-runtime-and-swarm.md. MySQL/MariaDB credential reconciliation targets the actual ready runtime task.

## Storage

Database volumes are persistent and registry-backed. force_reinit is an explicit destructive operation.

## Source map

- src/deployments/celery/tasks.py
- src/deployments/core/db_deployer.py
- src/deployments/core/swarm.py
- src/services/revisioning.py
- src/deployments/core/state/locks.py
- src/deployments/common/state_machine.py
- documentation/apps/services/
- documentation/apps/deploy/
