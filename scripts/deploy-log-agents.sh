#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

[ -f .env ] || {
    echo "ERROR: .env is required. Copy .env.example to .env first." >&2
    exit 2
}

env_value() {
    key=$1
    awk -v wanted="$key" '
        /^[[:space:]]*#/ { next }
        index($0, "=") > 0 {
            name = substr($0, 1, index($0, "=") - 1)
            if (name == wanted) {
                value = substr($0, index($0, "=") + 1)
                sub(/\r$/, "", value)
                found = 1
            }
        }
        END { if (found) print value }
    ' .env
}

LOG_INGEST_SHARED_TOKEN=$(env_value LOG_INGEST_SHARED_TOKEN)
[ -n "$LOG_INGEST_SHARED_TOKEN" ] || {
    echo "ERROR: LOG_INGEST_SHARED_TOKEN is empty. Run ./scripts/compose.sh up first." >&2
    exit 2
}
LOG_FORWARD_SOCKET_PATH=$(env_value LOG_FORWARD_SOCKET_PATH)
: "${LOG_FORWARD_SOCKET_PATH:=/run/passdeployer-logs/forward.sock}"
LOG_FORWARD_SOCKET_DIR=$(dirname "$LOG_FORWARD_SOCKET_PATH")
LOG_INGEST_NETWORK=$(env_value LOG_INGEST_NETWORK)
: "${LOG_INGEST_NETWORK:=deploy_log_ingest}"
FLUENT_BIT_IMAGE=$(env_value FLUENT_BIT_IMAGE)
: "${FLUENT_BIT_IMAGE:=fluent/fluent-bit:5.1.5-2}"
LOG_COLLECTOR_DISK_LIMIT=$(env_value LOG_COLLECTOR_DISK_LIMIT)
: "${LOG_COLLECTOR_DISK_LIMIT:=512M}"
LOG_COLLECTOR_CPU_LIMIT=$(env_value LOG_COLLECTOR_CPU_LIMIT)
: "${LOG_COLLECTOR_CPU_LIMIT:=0.50}"
LOG_COLLECTOR_MEMORY_LIMIT=$(env_value LOG_COLLECTOR_MEMORY_LIMIT)
: "${LOG_COLLECTOR_MEMORY_LIMIT:=128m}"

export LOG_INGEST_SHARED_TOKEN LOG_FORWARD_SOCKET_PATH LOG_FORWARD_SOCKET_DIR
export LOG_INGEST_NETWORK FLUENT_BIT_IMAGE LOG_COLLECTOR_DISK_LIMIT
export LOG_COLLECTOR_CPU_LIMIT LOG_COLLECTOR_MEMORY_LIMIT

swarm_state=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || true)
[ "$swarm_state" = "active" ] || {
    echo "ERROR: This multi-node agent mode requires an active Docker Swarm manager." >&2
    exit 2
}

# The main Compose project creates the private attachable overlay and connects
# deploy-web to it. Ensure the web endpoint exists before switching the agent.
docker inspect deploy-web >/dev/null 2>&1 || {
    echo "ERROR: deploy-web is not running. Start the control plane first." >&2
    exit 2
}

# The single-node Compose sidecar and the global service cannot bind the same
# Unix socket at the same time.
docker compose -f compose.yaml stop log-collector >/dev/null 2>&1 || true

# Prepare the current manager. Run the same command on every worker node before
# deploying; /run is node-local and is recreated on reboot.
sh "$ROOT_DIR/scripts/prepare-log-node.sh" "$LOG_FORWARD_SOCKET_DIR"

network_driver=$(docker network inspect --format '{{.Driver}}' "$LOG_INGEST_NETWORK" 2>/dev/null || true)
[ "$network_driver" = "overlay" ] || {
    echo "ERROR: $LOG_INGEST_NETWORK must be the private overlay network created by scripts/compose.sh." >&2
    exit 2
}

echo "Swarm nodes:"
docker node ls --format '  {{.Hostname}} ({{.Status}} / {{.Availability}})'
echo "Ensure scripts/prepare-log-node.sh has been run on every listed node."
docker stack config -c deploy/fluent-bit/swarm-stack.yaml >/dev/null
docker stack deploy -c deploy/fluent-bit/swarm-stack.yaml passdeployer-logs

echo "Deployed one Fluent Bit agent per eligible Swarm node."
