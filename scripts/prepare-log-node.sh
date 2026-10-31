#!/bin/sh
set -eu

# Docker's Fluentd logging driver and Fluent Bit must see the same host UDS.
# Install a tmpfiles rule so /run/passdeployer-logs is recreated after reboot.
SOCKET_DIR=${1:-/run/passdeployer-logs}
case "$SOCKET_DIR" in
    /run/*) ;;
    *) echo "The log socket directory must be under /run." >&2; exit 2 ;;
esac
case "/$SOCKET_DIR/" in
    */../*) echo "Invalid log socket directory." >&2; exit 2 ;;
esac
case "$SOCKET_DIR" in
    *[!A-Za-z0-9_./-]*) echo "Invalid characters in log socket directory." >&2; exit 2 ;;
esac
RULE=/etc/tmpfiles.d/passdeployer-logs.conf

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root to prepare the Docker logging socket directory." >&2
    if command -v sudo >/dev/null 2>&1; then
        exec sudo sh "$0" "$@"
    fi
    exit 1
fi

mkdir -p /etc/tmpfiles.d
printf 'd %s 0755 root root - -\n' "$SOCKET_DIR" > "$RULE"

if command -v systemd-tmpfiles >/dev/null 2>&1; then
    systemd-tmpfiles --create "$RULE"
else
    mkdir -p "$SOCKET_DIR"
    chmod 0755 "$SOCKET_DIR"
fi

[ -d "$SOCKET_DIR" ] || {
    echo "Failed to create $SOCKET_DIR" >&2
    exit 1
}

echo "Prepared Docker/Fluent Bit log socket directory: $SOCKET_DIR"
