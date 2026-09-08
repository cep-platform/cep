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

# Create the network CA (required before signing host certificates)
uv run cep network sign mynetwork

# Create lighthouse (first host must be lighthouse)
uv run cep host create mynetwork server --am-lighthouse --public-ip 203.0.113.1

# Connect lighthouse
uv run cep host connect mynetwork server

# Additional hosts can be regular (non-lighthouse)
uv run cep host create mynetwork laptop
uv run cep host connect mynetwork laptop
# create host config as a bundle
uv run cep host create mynetwork laptop --bundle
```

## CLI Commands

### Network

Before you start, make sure `CEP_SERVER_URL` is pointing to your server in .env and `CEP_SERVER_TOKEN` is set correctly

```bash
uv run cep network create <name>        # Create a network
uv run cep network sign <name>          # Create the network CA (required before signing host certificates)
uv run cep network list                 # List networks
uv run cep network show <name>          # Show network details
uv run cep network delete <name>        # Delete a network
```

> **Order matters:** run `network create` before `network sign`, and `network sign` before any `host create` (which signs host certificates against the network CA).

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

## Unit Tests

The test suite uses [pytest](https://pytest.org) and covers the server routers, CLI commands, data models, utility functions, and generated artifacts. All tests run without a live server — HTTP clients and subprocesses are mocked.

### Setup

Install the dev dependencies (pytest and pytest-cov are in the `dev` group):

```bash
uv sync --group dev
uv pip install -e .
```

### Running tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=cep --cov-report=term-missing

# Run a specific file or test
uv run pytest tests/test_server_network.py
uv run pytest tests/test_cli_host.py::TestHostCreate
```

### Test structure

| File | What is tested |
|------|----------------|
| `tests/conftest.py` | Shared fixtures (isolated DB, mocked DNS, TestClient, CliRunner) |
| `tests/test_datamodels.py` | Pydantic model validation and serialization roundtrips |
| `tests/test_utils.py` | `parse_stdout`, `get_platform`, `extract_archive`, `get_template_path` |
| `tests/test_storage_docker.py` | `Pool` / `Volume` filesystem operations and error handling |
| `tests/test_server_utils.py` | Network and storage DB load/save roundtrips |
| `tests/test_server_network.py` | `/network` router via FastAPI `TestClient` |
| `tests/test_server_host.py` | `/host` router via FastAPI `TestClient` |
| `tests/test_apps_docker.py` | `ComposeConfig` and `Docker` class methods (templates, deployment file management) |
| `tests/test_appstore_server.py` | Appstore FastAPI routes (`/health`, `/list`, `/deploy`, `/clear`, etc.) |
| `tests/test_cli_bundle.py` | `CepBundle` metadata generation and `.cepbundle` zip artifact structure |
| `tests/test_cli_dns.py` | `NebulaDNS` helpers and `dns` CLI commands |
| `tests/test_cli_network.py` | `network` CLI commands via Typer `CliRunner` |
| `tests/test_cli_host.py` | `host` CLI commands via Typer `CliRunner` |
| `tests/test_cli_apps.py` | `apps deploy/list/store/targeted-destroy/clear` CLI commands |
| `tests/test_cli_storage.py` | `storage pool` and `storage volume` CLI commands |

> **Note:** `CEP_SERVER_TOKEN` is automatically cleared during server tests so the test client does not need auth credentials.
