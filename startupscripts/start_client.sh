#!/bin/sh
set -e

# Works both on the host (cep installed in the uv venv) and inside the cep
# image (bare `cep` on PATH, no uv there).
if command -v cep >/dev/null 2>&1; then
  CEP="cep"
else
  CEP="uv run cep"
fi

cat "$(dirname "$0")/client_banner.txt"

sleep 5

# Wait until the main server is reachable

until $CEP network list; do
    echo "Main server not yet online, retrying in 4"
    sleep 4
done

NETWORK_NAME="${NETWORK_NAME:-cepnet}"
HOST_NAME="${HOST_NAME:-mainserver}"

$CEP network create "$NETWORK_NAME" --no-dns

$CEP host create "$NETWORK_NAME" "$HOST_NAME" \
    --am-lighthouse --public-ip "$LIGHTHOUSE_STABLE_IP"

$CEP host connect "$NETWORK_NAME" "$HOST_NAME" --detach
# pid=$!

until ip a | grep -q nebula; do
    sleep 0.5
done

$CEP dns start "$NETWORK_NAME"
# wait "$pid"
