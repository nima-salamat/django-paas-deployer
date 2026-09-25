# Revisions, Environment and Secrets

## Revision

Revision creation freezes effective executable configuration.

Historical revisions are immutable.

## Environment

Variables may be plain values or ServiceSecret-backed values. Runtime compilation resolves enabled variables into process definitions.

## Secrets

Secrets have immutable versions. Revisions reference exact versions so later secret rotation does not rewrite history.

## Rollback

Rollback targets an existing revision and creates a new deployment operation. It does not mutate the previous revision.

## Build secrets

Build-scoped secrets are rejected until the build backend supports secure BuildKit secret mounts.
