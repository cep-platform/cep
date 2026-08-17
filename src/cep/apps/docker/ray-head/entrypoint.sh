#!/usr/bin/env bash
set -euo pipefail

NEBULA_CONFIG="${NEBULA_CONFIG:-/etc/nebula/config.yml}"
RAY_PORT="${RAY_PORT:-6379}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8265}"

HOST_IP=$(getent hosts host.docker.internal | awk '{print $1; exit}')
if [ -z "$HOST_IP" ]; then
    HOST_IP=$(ip route show default | awk '{print $3; exit}')
fi

CONFIG_COPY="/tmp/nebula-config.yml"
python3 -c "
import yaml, os, sys
with open('$NEBULA_CONFIG') as f:
    config = yaml.safe_load(f)
pki = config.get('pki', {})
for key in ('ca', 'cert', 'key'):
    val = pki.get(key, '')
    if val and '/' in val:
        pki[key] = '/etc/nebula/' + os.path.basename(val)
with open('$CONFIG_COPY', 'w') as f:
    yaml.dump(config, f)
"
sed -i "s/127\.0\.0\.1/${HOST_IP}/g" "$CONFIG_COPY"

echo "Starting Nebula with config: $CONFIG_COPY (host IP: $HOST_IP)"
nebula -config "$CONFIG_COPY" &
NEBULA_PID=$!

cleanup() {
    echo "Shutting down Nebula (pid $NEBULA_PID)..."
    kill "$NEBULA_PID" 2>/dev/null || true
    wait "$NEBULA_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Waiting for Nebula interface..."
TIMEOUT=30
ELAPSED=0
while ! ip link show nebula1 >/dev/null 2>&1; do
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: Nebula interface nebula1 did not appear within ${TIMEOUT}s" >&2
        exit 1
    fi
done
echo "Nebula interface nebula1 is up"

echo "Starting Ray head on port ${RAY_PORT}"
exec ray start \
    --head \
    --block \
    --port="${RAY_PORT}" \
    --dashboard-port="${DASHBOARD_PORT}" \
    --dashboard-host=0.0.0.0
