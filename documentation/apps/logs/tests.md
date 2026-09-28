# logs contracts and tests

| Test | Protected behavior | Invariant |
|---|---|---|
| test_fingerprint.py | replay/deduplication | one source line does not become many rows after reconnect |
| test_isolation.py | service/tenant separation | logs for one service cannot leak to another |
| test_policy.py | quota/retention decisions | commercial logging policy remains enforced |
| test_resilience.py | reconnect/lease failures | collectors recover without losing ownership semantics |
| test_resilience_matrix.py | failure combinations | failure behavior remains bounded |
| test_resilience_scenarios.py | end-to-end collector scenarios | restart/stale collector cases remain safe |
| test_stream_modes.py | stream identity/mode behavior | stream keys remain stable and scoped |

When changing log IDs, fingerprints, leases or DB routing, read all four areas: ingestion, model, query and retention.
