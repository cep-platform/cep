#!/bin/sh
# Generate the certs on the 
incus remote generate-certificate

TOKEN=$(incus config trust add cep-appstore | tail -1)

incus --project cep exec appstore -- incus remote add 10.0.100.1 --accept-certificate --token $TOKEN
incus --project cep exec appstore -- incus remote switch 10.0.100.1
