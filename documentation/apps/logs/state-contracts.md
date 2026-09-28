# logs state and choice contracts

## Stream lifecycle

A ServiceLogStream has collector ownership/lease and replay cursor state. Lease expiry is a recovery signal, not proof that stored logs are invalid.

## Levels/modes

ServiceLogEntry carries level/mode metadata used by ingestion and query/retention. Exact accepted values follow the ingestion policy in src/logs/ingestion.py; do not widen them without corresponding parser/tests changes.

## Usage

Current and daily counters distinguish ingested, dropped and deleted bytes/entries. Unknown usage must remain unavailable rather than zero.
