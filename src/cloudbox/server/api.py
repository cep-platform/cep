from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from io import BytesIO
import zipfile

from cloudbox.nebula.nebula import Network, _list_networks

app = FastAPI()

@app.get("/listNetworks")
def list_networks():
    return _list_networks()


@app.get("/createNetwork")
def create_network():
    network = Network()
    return network.name


@app.get("/listNetworks")
def list_networks():
    return _list_networks()


@app.get("/createHost")
def create_host(network_name: str, host_name: str):

    network = Network(name=network_name)
    # Simulated config files (you can load these from disk/db)
    host = network.create_host(host_name, is_lighthouse=False)

    # Create zip in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, path in host.config_files.items():
            with open(path, 'r') as f:
                content = f.read()
            zip_file.writestr(filename, content)

    # Prepare for streaming
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=configs.zip",
            "Cache-Control": "no-store",
        }
    )

