#!/bin/sh
set -e

cat /app/client_banner.txt

sleep 5
# sleep until the server is reachable
while ! uv run cep network list; do
    echo "Main server not yet online, retrying in 4"
    sleep 4
done

# Get network name from env variable or default
NETWORK_NAME="${NETWORK_NAME:-cepnet}"
HOST_NAME="${HOST_NAME:-mainserver}"

# Create an initial network
uv run cep network create "$NETWORK_NAME" --no-dns

# Create a user for the server
uv run cep host create "$NETWORK_NAME" "$HOST_NAME" --am-lighthouse --public-ip $PUBLIC_IP
uv run cep host connect "$NETWORK_NAME" "$HOST_NAME" &

pid=$!
# Wait until service is ready
until ip a | grep nebula; do
  sleep 0.5
done

uv run cep dns start "$NETWORK_NAME"
wait "$pid"
