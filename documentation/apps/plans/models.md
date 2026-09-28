# plans models

## Plan

Plan is the customer-facing policy envelope.

| Field | Semantics |
|---|---|
| name | Choice among Bronze/Silver/Gold/Diamond. Commercial tier label; written by staff/admin. |
| platform | Choice from PLATFORM_CHOICES. Determines which Service technology family the plan supports. |
| max_cpu | vCPU ceiling consumed by Service/deployment policy. Tenant configuration cannot increase it. |
| max_ram | MB memory ceiling consumed by execution/resource policy. |
| max_storage | GB logical storage allocation ceiling; services converts it to MiB for volume accounting. |
| price_per_hour | Customer-facing hourly price in Toman. Derived day/month values are properties, not stored fields. |
| storage_type | HDD/SSD commercial/storage class. |
| plan_type | APP/DB/READY. Used to constrain compatible Service/application selection. |
| log_retention_days | Optional runtime-log retention override. Null means inherit platform/default. |
| log_storage_mb | Optional per-Service persistent-log quota. Null inherits default. |
| log_ingest_bytes_per_sec | Optional ingestion ceiling; null inherits. |
| persistent_logging | Nullable override controlling persistent runtime logs; null inherits. |
| realtime_logging | Nullable override controlling realtime log delivery; null inherits. |
| log_quota_behavior | fifo_delete, drop_new or realtime_only; blank inherits platform policy. |

## Authority

Plan values are operator-managed policy. Service and deployment code consume them; Plan does not create runtime resources.

## Lifecycle

Admin CRUD invalidates plan caches. Applying a plan to a Service is an explicit domain operation. Immediate application may queue a new deployment when the Service has an active revision; it never rewrites an old revision.

## Invariants

Resource ceilings are enforced by consumers. A tenant cannot use a serializer or JSON config field to raise max_cpu/max_ram/max_storage. Logging limits are separate from Service disk quota.

Source: src/plans/models.py.
