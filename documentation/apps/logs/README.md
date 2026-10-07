# logs

## Purpose

logs owns runtime/service log ingestion, persistence, quota/retention, collector leases, deduplication and health.

## Why this boundary exists

Runtime output is an ongoing data stream with reconnect/deduplication/retention semantics. DeployLog is lifecycle-event history and belongs to deploy. Keeping them separate prevents two different event models from being merged.

## Responsibilities

ServiceLogStream; ServiceLogEntry; usage accounting; collector heartbeat/lease; ingestion and fingerprints; retention; realtime log publication; service/admin query/export support.

## Non-responsibilities

Deploy lifecycle state/logs are deploy/deployments. Service desired configuration is services.

## Documents

- [models.md](models.md)
- [background.md](background.md)
- [tests.md](tests.md)

There is no standalone /logs/ router; runtime log APIs are mounted through services and deployment-event APIs through deploy.

## Security

Log access is authorized by the owning Service/share boundary before log query/export. Scalar ids are used because deployment logs may be isolated in another database.

## Invariants

1. Runtime logs and deployment events remain separate.
2. Replayed output is deduplicated.
3. Stream lease identifies the writer.
4. Unknown usage is not zero.
5. Retention/quota effects are accounted.

## Reading order

models.md -> background.md -> owning API documentation.

## Contract references

- [API reference](api.md)
- [Complete model field reference](field-reference.md)
