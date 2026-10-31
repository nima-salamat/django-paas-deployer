#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ ! -f .env ]; then
    echo "ERROR: .env is missing. Copy .env.example to .env first." >&2
    exit 2
fi

echo "Swarm runtime logging driver migration"
echo "  No flag: inspect managed services (dry-run)"
echo "  --apply: update existing services to the requested driver"
echo "  --driver json-file --apply: roll back to Docker's local driver"
echo

exec "$ROOT_DIR/scripts/compose.sh" exec -T web \
    python manage.py migrate_runtime_log_driver "$@"
