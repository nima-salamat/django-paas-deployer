# Ready-to-Deploy Application Audit

## Recovery regenerated generated secrets

Root cause: recovery re-ran catalog resolution, allowing generator fields and changed catalog sources to reinterpret an existing installation.

Architectural cause: the coordinator did not have a sufficiently authoritative persisted graph.

Fix: installation creation persists `_application_orchestration` in `ApplicationInstance.definition_snapshot`; recovery loads only that graph.

Regression: `test_executor_ignores_mutable_service_dependency_metadata` and `test_installation_snapshot_is_immutable`.

## Secret references were destroyed during compilation

Root cause: catalog rendering replaced `${secret.*}` before materialization.

Architectural cause: resolution mixed secret value substitution with structural compilation.

Fix: configuration and service-host references are rendered while secret references survive until ServiceSecret materialization. Composite environment expressions are stored as encrypted ServiceSecrets.

Regression: compiler and real-installation secret tests in `test_ready_application_architecture.py`.

## All resolved secrets were copied to every child

Root cause: installation iterated over the entire resolved secret map for each Service.

Fix: only secret references found in a child's supported runtime inputs are materialized on that Service.

Regression: `test_secrets_are_scoped_to_referencing_services`.

## DB catalog children were rejected

Root cause: `_find_plan()` accepted only APP/READY plans.

Architectural cause: catalog service role/platform/plan type were not connected to the repository's existing DB deployment path.

Fix: DB children select a platform-matched DB Plan and create normal Service/Deploy rows. The existing deployment engine routes DB platforms to DBDeployer.

Regression: real Mattermost materialization and DB process tests.

## Stale coordinator claims could execute

Root cause: a gate task accepted an empty/replaced dispatch claim.

Fix: gate tasks require an exact task-token match; queue failures clear both dispatch timestamp and token.

Regression: coordinator adversarial contract tests and task-source checks.

## Required failure left pending siblings

Root cause: application status became FAILED without terminalizing pending child Deploys.

Fix: required failure cancels pending children and requests cancellation for active siblings; optional dependency failure blocks downstream optional nodes.

Regression: `test_required_failure_cancels_pending_siblings`.

## Generic IntegrityError became name conflict

Root cause: every IntegrityError from ApplicationInstance creation was translated.

Fix: only the `(user, slug)` uniqueness constraint is mapped to ApplicationNameConflict; unrelated integrity errors propagate.

Regression: the PostgreSQL transaction-race test.

## Catalog child deletion could orphan the parent

Root cause: generic Service deletion had no application ownership boundary.

Fix: ApplicationInstanceService now protects child Service/Deploy bindings at the database layer; user/admin Service APIs reject catalog-managed child deletion.

Regression: `test_catalog_child_service_delete_is_rejected`.

## Transaction/storage limitation

Django database rollback cannot roll back object storage or Docker state. Installation archive writes are tracked and explicitly deleted on materialization failure. Docker resources remain owned by the normal Service/deployment lifecycle.

## Remaining limitations

- Runtime Docker/Celery integration requires the repository's real Docker daemon, broker and deployment environment.
- Physical storage/quota enforcement remains governed by the existing Service/Volume/runtime policy rather than the catalog coordinator.
- Database-resource bindings are not synthesized for catalog DB children because those children are themselves managed DB Services executed by DBDeployer; DatabaseResource remains a separate managed-resource abstraction.