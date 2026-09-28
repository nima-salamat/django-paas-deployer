# plans state and choice contracts

## Plan type

APP = application workload plan; DB = database plan; READY = ready-made/catalog-oriented plan.

## Storage

SSD/HDD selects the commercial/storage class. max_storage is the customer-facing Service allocation ceiling; it is not a Docker filesystem quota by itself.

## Platform

platform is constrained by core.global_settings.config.PLATFORM_CHOICES and identifies the technology/engine family a plan supports.

## Logging policy

log_retention_days, log_storage_mb and log_ingest_bytes_per_sec are optional overrides. Null means inherit the platform/default policy. log_quota_behavior may be fifo_delete, drop_new or realtime_only; blank means inherit.

See ../../deployments/04-build-and-platforms.md for execution-resource policy separation.
