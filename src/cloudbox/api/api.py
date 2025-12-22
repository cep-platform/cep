from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from io import BytesIO
import zipfile

from cloudbox.nebula.nebula import Network

app = FastAPI()
network = Network()

network.create_host("lh",
                    is_lighthouse=True,
                    public_ip='fd42:f8f4:bee9:96d7:1266:6aff:fe96:4a1c',
                    )


@app.get("/createHost")
def create_host():

    # Simulated config files (you can load these from disk/db)
    host = network.create_host('testhost', is_lighthouse=False)

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

