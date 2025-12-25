usage:

```
uv sync
uv pip install -e .

# start api
uv run fastapi dev src/cloudbox/api
```


separation of concerns:

server:
    ca
    network cidr
    ipam
    groups / roles
    lighthouse registry
    cert signing
    policy enforcement

host:
    key generation
    public key upload
    nebula cert storage
    local nebula.yml rendering
    nebula process lifecycle

