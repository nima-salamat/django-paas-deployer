#!/bin/sh
set -eu

if ! command -v python >/dev/null 2>&1; then
  echo "Python is required." >&2
  exit 2
fi

python scripts/run_ready_app_integration.py "$@"
