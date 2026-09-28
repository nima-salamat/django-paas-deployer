# logs background behavior

## Ingestion

ingestion.get_or_create_stream resolves a logical stream, acquire_lease claims collector ownership, heartbeat_lease extends it, and ingest_lines prepares/redacts/deduplicates lines before persistence and realtime publication.

Fingerprints participate in duplicate suppression. A replay after collector reconnect must not multiply usage or log rows.

## Retention and usage

retain_service deletes records according to the service logging policy. usage.bump_ingest/bump_drop/bump_delete maintain current and daily accounting. reconcile_usage repairs drift in bounded batches.

## Scheduled work

retain_all_services runs retention across services. reconcile_usage runs periodic accounting repair. Collector heartbeat is observed to detect stale collectors.

## Realtime

publish_log_events sends viewer-scoped realtime notifications; persistence remains authoritative.

## Tests as contracts

test_fingerprint.py protects deduplication; test_isolation.py protects service separation; test_policy.py protects retention/quota policy; resilience tests protect reconnect, lease and duplicate scenarios; test_stream_modes.py protects stream identity/mode semantics.
