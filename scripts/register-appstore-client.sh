#!/bin/sh
# Generate the certs on the 
incus remote generate-certificate 2>/dev/null

TOKEN=$(incus config trust add cep-appstore | tail -1)

incus --project cep exec cep-appstore -- incus remote add 10.0.100.1 --accept-certificate --token $TOKEN
incus --project cep exec cep-appstore -- incus remote switch 10.0.100.1
