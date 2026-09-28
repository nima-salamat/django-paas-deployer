# docs contracts and tests

| Test | Protected behavior |
|---|---|
| test_ordering.py | deterministic category/document ordering |
| test_public_assets.py | public asset capability/publication rules and invalid-auth-header resilience |

Public documentation APIs are intentionally published-only; admin permission changes must not accidentally weaken public asset handling.
