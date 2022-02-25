import uvicorn

from openpype.api.server import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="localhost",
        port=8001
    )
