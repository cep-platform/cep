# Cep

Cep is an application for securely deploying web apps on a server. It creates and manages [Nebula](https://github.com/slackhq/nebula) peer-to-peer VPN networks and deploys Docker containers for web applications.

## Features

- **Network Management**: Create and manage Nebula VPN networks
- **Host Management**: Create and connect hosts to networks
- **App Deployment**: Deploy Docker containers via the app store
- **Internal DNS**: Unbound-based internal DNS resolution

## Architecture

Cep consists of four components:

| Component | Port | Description |
|-----------|------|------------|
| cep-main | 8000 | FastAPI server - network/host/storage/DNS management |
| cep-appstore | 8000 | FastAPI server - Docker container deployment |
| cep-client | - | Nebula peer connecting to VPN network |
| cep-dns | 8053 | Unbound DNS for internal resolution |

## Quick Start

### Docker (Recommended)

```bash
cp .env.example .env
# Make sure to set LIGHTHOUSE_STABLE_IP

uv sync
uv pip install -e .

docker build . -t cep:latest
docker compose up -d

uv run cep network list
```

### Manual (Development, skip unless docker deployment fails for some reason)

Requires three terminal sessions:

**Terminal 1** - Main server:
```bash
export CEP_SERVER_TOKEN=your_secure_token
uv sync
uv run cep server run
```

**Terminal 2** - App store (requires docker.sock):
```bash
uv sync
uv run cep apps run
```

**Terminal 3** - Client:
```bash
# Create network
uv run cep network create mynetwork --no-dns

# Create lighthouse (first host must be lighthouse)
uv run cep host create mynetwork server --am-lighthouse --public-ip 203.0.113.1

# Connect lighthouse
uv run cep host connect mynetwork server

# Additional hosts can be regular (non-lighthouse)
uv run cep host create mynetwork laptop
uv run cep host connect mynetwork laptop
```

## CLI Commands

### Network

Before you start, make sure `CEP_SERVER_URL` is pointing to your server in .env and `CEP_SERVER_TOKEN` is set correctly

```bash
uv run cep network create <name>        # Create a network
uv run cep network list                 # List networks
uv run cep network show <name>       # Show network details
uv run cep network delete <name>       # Delete a network
```

### Host
```bash
uv run cep host create <network> <host> [--am-lighthouse --public-ip <ip>]
uv run cep host connect <network> <host>
uv run cep host disconnect
uv run cep host list <network>
uv run cep host show <network> <host>
uv run cep host delete <network> <host>
```

### Apps
```bash
uv run cep apps list                  # List available app templates
uv run cep apps deploy <app>          # Deploy an app
```

### DNS
```bash
uv run cep dns start <network>        # Start DNS for network
uv run cep dns stop               # Stop DNS
uv run cep dns add <name> <ip>   # Add DNS record
uv run cep dns remove <name>     # Remove DNS record
```

## Environment Variables

| Variable | Description |
|----------|------------|
| CEP_SERVER_TOKEN | Token for main server authentication |
| DNS_TOKEN | Token for DNS server authentication |
| CEP_SERVER_URL | URL of main server for client |
| LIGHTHOUSE_STABLE_IP | Public IP of the host |

## About Lighthouses

A lighthouse is a host with a stable public IP that coordinates connections between hosts behind NAT. It enables UDP hole punching for peer-to-peer connectivity.

- The first host in a network must be a lighthouse
- In Docker deployment, the server itself acts as the lighthouse
- For connectivity outside your home network, run a lighthouse on a public VPS with a stable IP

## Security Considerations

- The app store requires access to the Docker socket (`/var/run/docker.sock`) - this is a known privilege escalation vector
- Token-based authentication is used between components
- In production, isolate the app store in its own security context
