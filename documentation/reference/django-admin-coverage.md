# Django Admin model coverage

Django Admin and Wagtail are intentionally different surfaces.

## Django Admin contract

Every concrete model owned by the product apps is registered in the Django Admin site. This surface is the complete database/operator view: it is appropriate for inspection, controlled configuration and low-level operational troubleshooting.

The registration policy is not "everything is writable":

| Model class | Django Admin policy |
|---|---|
| Identity/configuration models | Editable when model invariants make direct editing safe. |
| Runtime state, deployment journals, logs and audit history | Read-only. |
| Secrets, credentials and token material | Read-only, with secret payload fields hidden where appropriate. |
| Wagtail Page models | Visible read-only for database inspection; Wagtail remains the canonical editorial UI. |
| Child/binding records with lifecycle ownership | Read-only unless their owning workflow explicitly supports mutation. |

The shared implementation lives in `src/core/django_admin.py`. The project-wide regression contract is `src/core/tests/test_django_admin_coverage.py`.

The regression test discovers project-owned apps from installed app-config paths inside `src/`; it does not depend on a manually maintained allowlist. It checks both registration and deliberate admin configuration, and verifies that shared read-only policies remain non-mutating.

## Wagtail contract

Wagtail is not required to expose every database model. It is the editorial/operator workspace for selected domain objects, site settings and operational inspection views. Its model registration is intentionally narrower and can be read-only for runtime state.

Therefore a model being absent from Wagtail is not evidence that it is missing from the product. The complete persistence surface is enforced by Django Admin instead.

## Current coverage

The current first-party model apps include:

- agent
- app_catalog
- auth_users
- cms
- core
- custom_emails
- deploy
- docs
- logs
- messenger
- plans
- services
- tickets
- users

The test's discovery is deliberately not limited to this inventory, so adding another first-party app will not silently remove it from the coverage contract. Framework models outside the repository source tree are not part of this contract.

## Sensitive data

Django Admin registration must not make plaintext secret material easier to expose. Token hashes, credential hashes, encrypted secret payloads and deployment secret configuration are hidden or read-only. Operational audit/history models are not deletable from the generic Django Admin UI.

## Deletion and lifecycle

Django Admin does not bypass domain deletion boundaries. In particular, active deployments must be cancelled/converged before destructive account or deployment deletion, Service-owned runtime cleanup remains under the Service signals, and Messenger/session caches have explicit invalidation paths.
