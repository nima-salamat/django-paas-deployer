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


# Return the Docker networks attached to a container, one name per line.
container_networks() {
    docker inspect --format '{{range $name, $config := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$1" 2>/dev/null
}

has_network() {
    printf '%s\n' "$2" | grep -F -x -q -- "$1"
}

# During shared-Postgres starts, make sure Compose connects to the network that
# actually contains the existing PostgreSQL container. This avoids a Django
# restart loop when MATRIX_DOCKER_NETWORK was copied from a different install.
preflight_matrix_postgres_network() {
    compose_command=""
    for arg in "$@"; do
        case "$arg" in
            up|start|restart|run|create) compose_command=$arg; break ;;
        esac
    done
    [ -n "$compose_command" ] || return 0

    postgres_networks=$(container_networks "$MATRIX_POSTGRES_HOST") || {
        echo "ERROR: Cannot inspect Docker container '$MATRIX_POSTGRES_HOST'. Shared PostgreSQL mode expects the existing Matrix PostgreSQL container to be present." >&2
        echo "Check MATRIX_POSTGRES_HOST and run: docker ps --format '{{.Names}}'" >&2
        return 2
    }

    case "$MATRIX_DOCKER_NETWORK" in
        bridge|host|none)
            echo "ERROR: MATRIX_DOCKER_NETWORK='$MATRIX_DOCKER_NETWORK' is a special Docker network and does not provide the user-defined network DNS required for '$MATRIX_POSTGRES_HOST'." >&2
            return 2
            ;;
    esac

    if ! has_network "$MATRIX_DOCKER_NETWORK" "$postgres_networks"; then
        synapse_networks=$(container_networks synapse 2>/dev/null || true)
        candidates=""
        for candidate in $postgres_networks; do
            case "$candidate" in bridge|host|none) continue ;; esac
            if [ -n "$synapse_networks" ] && ! has_network "$candidate" "$synapse_networks"; then
                continue
            fi
            candidates="${candidates}${candidates:+
}$candidate"
        done

        candidate_count=$(printf '%s\n' "$candidates" | awk 'NF { count++ } END { print count + 0 }')
        if [ "$candidate_count" -ne 1 ]; then
            echo "ERROR: MATRIX_DOCKER_NETWORK='$MATRIX_DOCKER_NETWORK' does not contain '$MATRIX_POSTGRES_HOST', and the correct shared network is not unambiguous." >&2
            echo "Networks attached to '$MATRIX_POSTGRES_HOST':" >&2
            printf '%s\n' "$postgres_networks" >&2
            if [ -n "$synapse_networks" ]; then
                echo "Networks attached to 'synapse':" >&2
                printf '%s\n' "$synapse_networks" >&2
            fi
            echo "Set MATRIX_DOCKER_NETWORK in .env to the user-defined network shared by the Matrix PostgreSQL container and Synapse." >&2
            return 2
        fi

        MATRIX_DOCKER_NETWORK=$(printf '%s\n' "$candidates" | awk 'NF { print; exit }')
        echo "WARNING: MATRIX_DOCKER_NETWORK did not match '$MATRIX_POSTGRES_HOST'; using detected network '$MATRIX_DOCKER_NETWORK'." >&2
    fi

    if ! docker network inspect "$MATRIX_DOCKER_NETWORK" >/dev/null 2>&1; then
        echo "ERROR: Docker network '$MATRIX_DOCKER_NETWORK' is not present. Start the Matrix Compose project or set MATRIX_DOCKER_NETWORK to its existing network." >&2
        return 2
    fi

    export MATRIX_DOCKER_NETWORK
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

        MATRIX_DOCKER_NETWORK=$(setting MATRIX_DOCKER_NETWORK)
        : "${MATRIX_DOCKER_NETWORK:=matrix_matrix}"
        preflight_matrix_postgres_network "$@" || exit $?

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
