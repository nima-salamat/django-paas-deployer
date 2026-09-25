# Runtime logging modes

The runtime log subsystem resolves one effective policy per service. The collector is the only component that reads Docker logs; the service WebSocket only subscribes to collector fanout.

## Modes

The effective mode is derived from persistence, realtime delivery, and quota behavior:

- persistent_realtime: persist entries and publish them over Channels.
- persistent_only: persist entries; no realtime WebSocket fanout.
- realtime_only: publish sanitized ephemeral entries; no durable history for newly emitted lines.
- disabled: do not attach a collector to the service.

realtime_only is normalized to persistent_enabled=false so all layers observe the same effective behavior. Realtime-only lines go through the same normalization, redaction, truncation and level inference path as persistent lines before publication.

## Recovery and ordering

A ServiceLogStream represents one service/container runtime lifetime and is protected by a partial uniqueness constraint so only one active row exists for a service/container pair. Collector ownership is controlled by a lease.

Persisted WebSocket events use the exact inserted database row, including its database id and cursor. Cursors use ts + id as the stable ordering key; legacy ts + seq cursors remain decodable.

Catch-up demultiplexing preserves Docker stdout and stderr instead of collapsing both into stdout.

## History

The HTTP log API remains the historical/persistent interface. Its response exposes the effective logging mode and whether persistent history is available.

## Future work

The bounded in-process buffer is deliberately not a durable queue. The collector now shares one rate window across all streams of a service within the same collector process; a production deployment with multiple collectors still needs a Redis-backed distributed token bucket or equivalent coordination. Other next steps are a durable Redis/disk spool, explicit gap/sequence metadata for ephemeral realtime mode, compression or partitioning for large log stores, and server-side filter/search streams.