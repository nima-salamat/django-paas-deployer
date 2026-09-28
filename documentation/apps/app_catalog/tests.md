# app_catalog contracts and tests

| Test | Protected behavior | What breaks if violated |
|---|---|---|
| test_catalog_definitions.py | Catalog definition schema/normalization | invalid source definitions reach planning |
| test_catalog_sources.py | Source loading/resolution | wrong catalog variant/source becomes executable input |
| test_application_plan.py | ApplicationPlan structure | child Services/Deploys diverge from catalog intent |
| test_adversarial_contracts.py | unsafe/unsupported catalog inputs fail closed | catalog becomes a privileged runtime escape |
| test_compatibility.py | compatibility analyzer semantics | legacy catalog inputs resolve inconsistently |
| integration/test_ready_app_runtime.py | ready application uses normal runtime path | catalog silently becomes a second deployment implementation |
| test_installation_hardening.py | immutable recovery graph, secret stability, transactional materialization | recovery regenerates credentials or partial installs survive failure |
| recovery/reconciliation tests | coordinator restart/lost task recovery | installations remain stuck or duplicate children |

A catalog change must be tested as both a plan compiler change and a coordinator/runtime boundary change.


## Architecture-hardening coverage

The architecture suite covers immutable snapshot authority, real catalog secret-reference preservation, per-Service secret scope, DB-child materialization, required-failure convergence, catalog child deletion protection, and a PostgreSQL-only two-transaction installation race. These complement the catalog-wide compile/plan tests; compile success is not treated as proof of installation or runtime success.
