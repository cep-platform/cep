import re
import subprocess
import threading
from ipaddress import IPv6Network
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel


process_lock = threading.Lock()
process: subprocess.Popen | None = None


class AddAAAARequest(BaseModel):
    name: str
    ip: str


def extract_hostname_and_ip(local_data: str) -> tuple[str, str]:
    """
    Extract hostname and IP address from a Unbound-style local-data string.

    Example input:
        local-data: "laptop5.local. AAAA ::5"
    """
    pattern = r'"(?P<hostname>\S+)\s+\S+\s+(?P<ip>\S+)"'
    match = re.search(pattern, local_data)

    if not match:
        raise ValueError("Invalid local-data format")

    hostname = match.group("hostname").rstrip(".")
    ip = match.group("ip")

    return hostname, ip


def read_records(path: Path) -> dict[str, str]:
    return dict([
        extract_hostname_and_ip(line)
        for line in path.read_text().splitlines()
        if line.strip()[0] != '#'
        ])
    

def write_records(path: Path, config: dict[str, str]):
    path.write_text(
            '\n'.join(
                [
                    f'local-data: "{hostname}. AAAA {ip}"'
                    for hostname, ip in config.items()
                    ]
                )
            )


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/start")
def start(subnet: str = Body(..., embed=True)):
    config_template_path = Path('/opt/unbound/etc/unbound/unbound_template.conf')
    config_template = config_template_path.read_text()

    subprocess.run("unbound-control-setup", check=True)

    ip = str(next(IPv6Network(subnet).hosts()))

    config = (
            config_template
            .replace('{{HOST_SUBNET}}', str(subnet))
            .replace('{{HOST_IP}}', str(ip))
            )

    config_path = Path('/opt/unbound/etc/unbound/unbound.conf')
    config_path.write_text(config)
    
    global process
    with process_lock:
        if process and process.poll() is None:
            raise HTTPException(400, "Process already running")

        process = subprocess.Popen(["/unbound.sh"])

    return {"status": "started"}


@app.post("/stop")
def stop():
    global process
    with process_lock:
        if not process or process.poll() is not None:
            raise HTTPException(400, "No running process")

        process.terminate()  # or .kill()
        process.wait(timeout=5)
        process = None

    return {"status": "stopped"}


@app.post("/records")
def add_aaaa_record(aaaa_request: AddAAAARequest):

    # Add record
    records_path = Path('/opt/unbound/etc/unbound/a-records.conf')
    records = read_records(records_path)
    records[aaaa_request.name] = aaaa_request.ip
    write_records(records_path, records)

    with process_lock:
        if process and process.poll() is None:
            subprocess.run(["unbound-control", "reload"], check=True)

    return {"status": "added"}


@app.delete("/records/{name}")
def remove_host(name: str):

    # Add record
    records_path = Path('/opt/unbound/etc/unbound/a-records.conf')
    records = read_records(records_path)
    del records[name]
    write_records(records_path, records)

    # Reload Unbound
    with process_lock:
        if process and process.poll() is None:
            subprocess.run(["unbound-control", "reload"], check=True)

    return {"status": "reloaded"}
