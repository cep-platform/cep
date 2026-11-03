#!/bin/sh
# Generate the client certificate used to talk to the incus daemon
incus remote generate-certificate 2>/dev/null

TOKEN=$(incus config trust add cep-appstore | tail -1)

incus --project cep exec cep-appstore -- incus remote add 10.0.100.1 --accept-certificate --token $TOKEN
incus --project cep exec cep-appstore -- incus remote switch 10.0.100.1
