# plans

## Purpose

plans defines the customer-facing policy envelope for application/database Services: platform family, resource/storage ceilings, plan type, pricing and runtime-log limits.

## Why this boundary exists

Plan policy must be independent of the Docker/runtime implementation. Services consume the plan as a ceiling and deployments consume it as policy input; tenant configuration cannot raise those ceilings.

## Responsibilities

Plan persistence and choices; public plan reads; staff/admin management; applying a plan to a Service; plan-cache invalidation; exposing logging/storage/resource policy inputs.

## Non-responsibilities

Plan execution is not runtime orchestration. Docker/Swarm is deployments. Service desired configuration is services. Runtime log persistence is logs. User billing/account balance is users.

## Documents

- [models.md](models.md) — Plan fields and policy semantics.
- [api.md](api.md) — public/admin/apply routes.
- [serializers.md](serializers.md) — public versus admin representations.
- [state-contracts.md](state-contracts.md) — platform/plan/logging choice semantics.

## Lifecycle and policy boundary

Plan changes are operator/admin changes. Service.clean blocks plan changes during queued/deploying/stopping. Immediate application can queue a new deployment only when the Service has an active executable revision.

## Invariants

1. max_cpu/max_ram/max_storage are ceilings.
2. Tenant Service configuration cannot increase plan ceilings.
3. A plan change does not rewrite an old ServiceRevision.
4. Cache invalidation is derived infrastructure; the Plan DB row remains authoritative.
5. Plan policy must be followed into its consumers before adding a new field.

## Reading order

models.md -> api.md -> serializers.md -> state-contracts.md -> ../services/README.md -> ../../deployments/04-build-and-platforms.md.
