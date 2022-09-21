import uvicorn

from openpype.api.server import app
from openpype.config import pypeconfig

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=pypeconfig.http_listen_address,
        port=pypeconfig.http_listen_port,
        reload=True,
    )
