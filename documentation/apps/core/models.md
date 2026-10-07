# core models

## SystemSetting

Operator-configurable typed setting registry.

| Field | Meaning |
|---|---|
| key | Stable dotted setting key consumed by settings_service; changing it can break consumers. |
| value | Stored textual representation of the setting. Sensitive values are flagged rather than exposed by tenant APIs. |
| value_type | Determines cast_value() behavior (string/int/float/bool/JSON and current supported variants). |
| category | Admin grouping and filtering. |
| label / description | Operator-facing metadata. |
| is_secret | Presentation/security flag; secret values must not leak through generic API responses. |
| is_editable | Whether normal admin PATCH may change it; superuser can bypass the lock in the current API. |
| timestamps | Audit of setting creation/update. |

settings_service is the normal read/write adapter. A SystemSetting change can alter deployment/build/monitor/shell behavior, so callers should validate consumers before changing names or types.

## CoreSettings

Operator/deployment settings aggregate used by the platform configuration surface. Current fields include build-resource controls, volume-release/usage policy, deployment/queued/stop timeouts, monitor/recovery controls, base-image controls, shell controls and concurrency caps.

CoreSettings is operator state, not tenant Service configuration. Deployments consume these values as policy ceilings/timeouts.

## Source/authority rules

SystemSetting is durable operator configuration; Redis/cache is not an authority for it. Secret flags are metadata for safe admin presentation, not encryption by themselves; deployment/runtime secrets have separate handling in services/deployments.

Source: src/core/models.py, src/core/settings_service.py.

> **Complete field reference:** [field-reference.md](field-reference.md) lists every field explicitly declared in `src/core/models.py`, including type, null/blank behavior, defaults, constraints and purpose.
