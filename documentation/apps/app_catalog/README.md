# app_catalog

## Purpose

The app_catalog app turns curated application definitions into validated, multi-Service installation plans and coordinates creation of those child resources.

## Why this boundary exists

Ready-made applications often contain multiple cooperating services, generated configuration, secrets, persistent storage and networks. Catalog interpretation and installation coordination are a distinct lifecycle from an individual Service deployment. The boundary lets the catalog produce normal Services/Deploys instead of implementing a second container runtime.

## Responsibilities

Catalog/source loading; Compose normalization; compatibility analysis; variant/plan resolution; install validation; application snapshots; installation coordinator state; child Service/Deploy creation; cancellation and reconciliation.

## Non-responsibilities

Docker/Swarm runtime execution belongs to deployments. Long-term Service configuration belongs to services. Shared base-image policy belongs to deploy/deployments. Catalog installation does not replace the normal deployment pipeline.

## Documents

- [models.md](models.md) — ApplicationInstance and child binding field contract.
- [api.md](api.md) — every registered catalog/install route and side-effect chain.
- [serializers.md](serializers.md) — representation and secret masking.
- [background.md](background.md) — coordinator tasks, dispatch and recovery.
- [tests.md](tests.md) — planning/security/runtime contract tests.
- [ready-apps.md](ready-apps.md) — canonical Ready Apps publication, API, frontend contract, recipes and extension guide.

## Security boundary

Catalog definitions are validated before child creation. Unsupported privileged/host-escape semantics fail closed. secret_config is sensitive and never returned raw.

Ready Apps add a publication boundary: an application is public only when its definition declares `visibility: public`, its source is directly under `src/app_catalog/catalog/first_party/`, and every executable image reference satisfies the pinned-image policy. `CatalogPublication` can additionally hide a safe curated entry or override its featured flag. Public serializers expose only safe product metadata and user-editable configuration fields.

## Main lifecycle

```text
catalog source
 -> validated definition + variant
 -> ApplicationPlan
 -> ApplicationInstance
 -> child Service/Deploy
 -> normal ServiceRevision/deployments pipeline
 -> coordinator running/failed/cancelled
```

## Invariants

1. Catalog coordinates; deployments executes.
2. Stored definition/variant snapshot makes recovery deterministic.
3. Coordinator state and child Deploy state are separate.
4. Cancellation cannot silently continue dispatching children.
5. Generated secret material is never exposed by normal serializers.
6. Public Ready Apps never accept arbitrary tenant Compose authoring.
7. Ready App resource previews are produced by backend resolution rather than frontend calculations.

## Reading order

Read models.md -> api.md -> serializers.md -> background.md. For child runtime behavior also read ../services/README.md and ../deployments/README.md, then ../../deployments/execution/02-request-to-plan.md.

For the public application product, read ready-apps.md after api.md and serializers.md.

## Wagtail administration

Installed catalog applications are exposed in Wagtail under **Applications** as read-only coordinator records. `ApplicationInstance` shows safe identity/config/status/error metadata; `secret_config` is not exposed. `ApplicationInstanceService` is read-only coordinator provenance. **Cancel installation** requires `app_catalog.change_applicationinstance` and delegates to the existing `cancel_application_installation` task, with its established synchronous executor fallback.\n\nThe **Ready App publication** surface is the operator/editorial control for curated catalog visibility. It changes only `CatalogPublication.enabled` / `featured_override` / `notes`; the executable YAML/Compose recipe remains source-controlled.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)

For installation and Ready App specifics, also read [ready-apps.md](ready-apps.md) and [architecture.md](architecture.md).
