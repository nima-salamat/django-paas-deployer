# Service-Centric Runtime Reconciliation Report

## Scope and evidence

This report records the reconciliation of `refactor/service-centric-runtime` with
the fetched `origin/master` at commit `fca3a46`.

- `origin/master` contained 105 commits absent from the pre-rebase local base.
- The refactor contained 221 commits unique from the common history.
- The refactor was rebased onto current `origin/master`; the pre-rebase tip is
  retained as `safety/refactor-pre-rebase`.
- Master-side deploy-name scoping, Wagtail contrast/regression work, DRF
  throttling, migration checks, startup ownership, upload fixes, and shared
  backend-image changes were retained during conflict resolution.

## Findings

### Service domain restoration

`src/services/models.py` was not a migration marker or alternate model location.
It was the result of an accidental destructive commit sequence that replaced the
complete service domain with `RESTORE_FROM_LOCAL`. The last complete refactor
model snapshot was recovered from the refactor history immediately before that
sequence. It contains the service, process, immutable revision, configuration,
secret, endpoint, network, database, volume, sharing, and shell models. The
`lifecycle_generation` fence required by migration `0026` was restored explicitly.

### Migration and admin defects found during validation

- Django 5.2 requires `condition=` for `CheckConstraint`; both the service model
  and historical service migration `0012` used the obsolete `check=` keyword.
- The port-reservation historical migration contained an unnamed index, which
  prevents Django 5.2 from loading the migration state.
- Master’s deploy-name migrations and the refactor’s Swarm migration formed two
  `deploy` leaf nodes; merge migration `0018` now joins them.
- Swarm cluster/node models were registered by both bespoke and universal Wagtail
  admin paths; they are now excluded from universal discovery.
- The local environment cannot reach Compose PostgreSQL (`db`), so database
  migration execution remains an integration validation item.

### Current blockers

`python manage.py check` passes with existing Treebeard compatibility warnings.
`python manage.py makemigrations --check` now loads the graph but reports model
state drift across several apps. This must be reconciled before merge readiness;
generated migrations must be reviewed rather than accepted blindly.

## Implementation plan

1. Reconcile model state against migration history, starting with deploy and
   services, and add only intentional migrations for post-refactor model changes.
2. Validate service/revision/deployment lifecycle invariants and ensure all
   application and database deployment paths use the same revision-backed
   execution contract.
3. Audit concurrency fencing, ownership, cancellation, retry, rollback, and
   reconciliation paths for stale-worker and duplicate-delivery behavior.
4. Run focused regression suites, then the complete test suite and Compose/Swarm
   integration profile when the runtime is available.
5. Audit API/security/admin behavior and update documentation to match verified
   behavior. Keep the branch unmerged while any migration, runtime, or security
   uncertainty remains.
