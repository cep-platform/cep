#!/bin/sh
set -e

cat ./startupscripts/client_banner.txt

sleep 5

# Wait until the main server is reachable

until uv run cep network list; do
    echo "Main server not yet online, retrying in 4"
    sleep 4
done

NETWORK_NAME="${NETWORK_NAME:-cepnet}"
HOST_NAME="${HOST_NAME:-mainserver}"

uv run cep network create "$NETWORK_NAME" --no-dns

uv run cep host create "$NETWORK_NAME" "$HOST_NAME" \
    --am-lighthouse --public-ip "$LIGHTHOUSE_STABLE_IP"

uv run cep host connect "$NETWORK_NAME" "$HOST_NAME" --detach
# pid=$!

until ip a | grep -q nebula; do
    sleep 0.5
done

uv run cep dns start "$NETWORK_NAME"
# wait "$pid"
