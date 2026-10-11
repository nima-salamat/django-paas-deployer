#!/bin/sh
set -eu

# Always run Compose from the repository root so .env and relative bind mounts
# resolve the same way regardless of the caller's working directory.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR/.."

# Read one unquoted KEY=value from .env without sourcing it as shell code.
# Matrix PostgreSQL passwords should be generated as hex (e.g. openssl rand -hex 32).
dotenv_value() {
    key=$1
    [ -f .env ] || return 0
    awk -v wanted="$key" '
        /^[[:space:]]*#/ { next }
        index($0, "=") > 0 {
            name = substr($0, 1, index($0, "=") - 1)
            if (name == wanted) {
                value = substr($0, index($0, "=") + 1)
                sub(/\r$/, "", value)
                print value
                exit
            }
        }
    ' .env
}

setting() {
    key=$1
    value=$(printenv "$key" 2>/dev/null || true)
    if [ -n "$value" ]; then
        printf '%s' "$value"
    else
        dotenv_value "$key"
    fi
}

USE_MATRIX_POSTGRES=$(setting USE_MATRIX_POSTGRES)
case "$(printf '%s' "$USE_MATRIX_POSTGRES" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
        MATRIX_POSTGRES_HOST=$(setting MATRIX_POSTGRES_HOST)
        MATRIX_POSTGRES_PORT=$(setting MATRIX_POSTGRES_PORT)
        MATRIX_POSTGRES_USER=$(setting MATRIX_POSTGRES_USER)
        MATRIX_POSTGRES_PASSWORD=$(setting MATRIX_POSTGRES_PASSWORD)
        MATRIX_POSTGRES_MAIN_DB=$(setting MATRIX_POSTGRES_MAIN_DB)
        MATRIX_POSTGRES_LOG_DB=$(setting MATRIX_POSTGRES_LOG_DB)

        : "${MATRIX_POSTGRES_HOST:=synapse-postgres}"
        : "${MATRIX_POSTGRES_PORT:=5432}"
        : "${MATRIX_POSTGRES_USER:=paas_deployer}"
        : "${MATRIX_POSTGRES_MAIN_DB:=paas_deployer}"
        : "${MATRIX_POSTGRES_LOG_DB:=paas_deployer_logs}"

        if [ -z "$MATRIX_POSTGRES_PASSWORD" ] || [ "$MATRIX_POSTGRES_PASSWORD" = "replace-with-a-new-random-password" ]; then
            echo "ERROR: Set MATRIX_POSTGRES_PASSWORD in .env before enabling shared PostgreSQL." >&2
            exit 2
        fi

        # Compose environment overrides .env and each service's env_file. Use
        # separate logical databases and a dedicated non-Synapse role.
        export DB_HOST="$MATRIX_POSTGRES_HOST"
        export DB_PORT="$MATRIX_POSTGRES_PORT"
        export DB_NAME="$MATRIX_POSTGRES_MAIN_DB"
        export DB_USER="$MATRIX_POSTGRES_USER"
        export DB_PASSWORD="$MATRIX_POSTGRES_PASSWORD"

        export DEPLOYMENT_LOG_DB_HOST="$MATRIX_POSTGRES_HOST"
        export DEPLOYMENT_LOG_DB_PORT="$MATRIX_POSTGRES_PORT"
        export DEPLOYMENT_LOG_DB_NAME="$MATRIX_POSTGRES_LOG_DB"
        export DEPLOYMENT_LOG_DB_USER="$MATRIX_POSTGRES_USER"
        export DEPLOYMENT_LOG_DB_PASSWORD="$MATRIX_POSTGRES_PASSWORD"

        exec docker compose -f compose.yaml -f compose.matrix-postgres.yaml "$@"
        ;;
    *)
        # Keep the existing local-PostgreSQL deployment as the default.
        exec docker compose -f compose.yaml "$@"
        ;;
esac
