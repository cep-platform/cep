# Cloudbox (Needs an actual name)

Cloudbox is an application that does three things at the moment:
- Create and manage nebula peer to peer networks
- Create and manage host on these networks
- Manage and deploy docker containers to run webapps

It's purpose is to provide a easy to use, zero technical knowledge required way to securely deploy web apps on a server. To do this it uses [nebula](https://github.com/slackhq/nebula) to manage network access. Since nebula proves identity through mutual TLS, it is intended to be used as an identity source for the webapps through OIDC as well, but this is for later, when web app deployment and access is stable. 

You're currently in the branch for development of the app store, which, in order to deploy the webapps, manages a docker compose file and handles deployment. You can use it through some fastapi endpoints.
Since the app store requires access to the docker socket, it'll need to be easy to isolate later, as an exposed docker socket is a known privilege escalation vector
Because of this, the apps store can be ran separately from the main service. 

To install it for development
```
uv sync
uv pip install -e .
```

You can now run
```
uv run cloudbox --help
```

# Start api
```
uv run cloudbox server set-auth-token # not secure but good enough for now
uv run cloudbox server run  # start the main server
# in a different shell:
uv run cloudbox apps run  # start the app store server
```

You can now use the cli:
```
# run the cli
uv run cloudbox auth   # provide the url as follows: http://<ip/hostname/localhost>:8000 (no quotationmarks)
```

First create a network
```
# create a network
uv run cloudbox network create <networkname>
uv run cloudbox network list
```

Create a host:
```
# create a host and connect (first one needs to be a lighthouse)
uv run cloudbox host create <network-name> <host-name> [--am-lighthouse --public-ip <public-ip>]
uv run cloudbox host connect <network-name> <host-name>  # this requires sudo privileges
```

List available app templates:
```
uv run cloudbox apps list
```

Start an app:
```
uv run cloudbox apps deploy redis
```

That's it, destroying apps needs to be done using docker itself, it hasn't been added to the API yet.



## Architecture diagram
![Architecture Diagram](./assets/architecture.png)
