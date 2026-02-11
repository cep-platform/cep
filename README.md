# Cep

### intro
Cep is an application that does the following things at the moment:
- Create and manage nebula peer to peer networks
- Create and manage host on these networks
- Manage and deploy docker containers to run webapps
- Provide a CLI to interact with these services

It's purpose is to provide a easy to use, zero technical knowledge required way to securely deploy web apps on a server. To do this it uses [nebula](https://github.com/slackhq/nebula) to manage network access. Since nebula proves identity through mutual TLS, it is intended to be used as an identity source for the webapps through OIDC as well, but this is for later, when web app deployment and access is stable. 

## Get started
### installation
The easiest way to get started is by running the docker deployment.
```
docker build . -t cep:latest
docker compose up
```
This orchestrates the various parts of `cep` in a way that's intended to be the most secure. Specifically, it runs the `apps` service in a separate container with access to the docker socket. This is done because 
### CLI
Once the service is deployed, you can start using the CLI.
irst create a network
```
# create a network
uv run cep network create <networkname>
uv run cep network list
```

Create a host:
```
# create a host and connect (first one needs to be a lighthouse)
uv run cep host create <network-name> <host-name> [--am-lighthouse --public-ip <public-ip>]
uv run cep host connect <network-name> <host-name>  # this requires sudo privileges
```

The first host needs to be a lighthouse (a host with some stable ip). If you want to test if things work, you can create a lighthouse host and connect with it, but to actually test the connectivity, you'll need some additional hosts. Some ways to run a couple of hosts with different ips:
- a number of cloud instances
- a couple of vms (vmware, virt-manager, qemu, incus)
- Connect a bunch of old laptops to the same network

Incus is nice because it's super lightweight, but you could also set things up with virt-manager/virtualbox/vmware etc. 
You'll only need three hosts to test almost anything network related though: a lighthouse and two regular host to test host interactions.


### Apps
Currently you can do the following:
- list apps
- deploy one of those apps (meaning deploy the compose file managed on the host running the apps service)

`apps` currently deploys apps to serve on all interfaces (of the host on which you deploy the app store service), so you don't need to create or be connected to a nebula network to access the webapps. That's only for development use though, in the end networking and apps should integrate for security purposes.

List available app templates:
```
uv run cep apps store list
```

Start an app:
```
uv run cep apps deploy redis
```

You should now see redis when you run `docker ps`

That's it, destroying apps needs to be done using docker itself, it hasn't been added to the API yet.
```
docker ps -q | xargs docker stop
docker ps -aq | xargs docker rm
```

Check out the issues!

# Architecture
Cep consists of a number of parts:
### network

### hosts
#### standardized connection pack
#### Enrolment
#### auth
##### nebula certs
##### OIDC

### storage pools (if not supported by docker)
### apps
#### storage volumes
#### Reverse proxy
#### store

### DNS

### Clients
#### CLI
#### Webui
#### Hypha

### outpost



## Architecture diagram
![Architecture Diagram](./assets/architecture.png)
