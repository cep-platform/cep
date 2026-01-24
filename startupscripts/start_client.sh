#!/bin/sh
set -e

sleep 5
# sleep until the server is reachable
while ! uv run cloudbox network list; do
    echo "Main server not yet online, retrying in 4"
    sleep 4
done

# Get network name from env variable or default
NETWORK_NAME="${NETWORK_NAME:-cloudboxnet}"
HOST_NAME="${HOST_NAME:-mainserver}"

# Create an initial network
uv run cloudbox network create "$NETWORK_NAME"

# Create a user for the server
uv run cloudbox host create "$NETWORK_NAME" "$HOST_NAME" --am-lighthouse --public-ip $PUBLIC_IP
uv run cloudbox host connect "$NETWORK_NAME" "$HOST_NAME"

# Keep container running if needed
wait
