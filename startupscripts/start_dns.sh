#!/bin/sh

# Start minimal reload api
exec uvicorn api:app --host 0.0.0.0 --port 8053 &

sleep 5
while ! ip a show nebula1; do
    echo "nebula1 not up yet, retrying in 10s"
    sleep 10
done

# get the ip
IP=$(ip a show nebula1 | grep 'inet6 fd' | head -n1 | grep -oP 'fd[0-9a-f:]+')

# mkdir -p /usr/local/etc/unbound


# Populate the config with nebula ip
echo ##########################################
sed "s/{{HOST_IP}}/$IP/" /etc/unbound/unbound.conf
touch /opt/unbound/etc/unbound/unbound.conf
sed "s/{{HOST_IP}}/$IP/" /etc/unbound/unbound.conf > /opt/unbound/etc/unbound/unbound.conf 
echo ##########################################

unbound-control-setup

# Start unbound detached
unbound
