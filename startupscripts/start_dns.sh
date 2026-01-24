#!/bin/sh

# Install ip to get the nebula ip
apt-get update && apt-get install -y iproute2 && rm -rf /var/lib/apt/lists/*

# Wait for the nebula interface to come up
while ! ip a show nebula1; do
    echo "nebula1 not up, retrying in 1"
    sleep 1
done

# get the ip
IP=$(ip a show nebula1 | grep 'inet6 fd' | head -n1 | grep -oP 'fd[0-9a-f:]+')

mkdir -p /usr/local/etc/unbound

# Populate the config with nebula ip
sed "s/{{HOST_IP}}/$IP/" /etc/unbound/unbound.conf > /usr/local/etc/unbound/unbound.conf
unbound -d -c /usr/local/etc/unbound/unbound.conf
