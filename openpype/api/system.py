import time


async def restart_server():
    """Force the server to restart.

    This is a hackish way how to do that (using uvicorn auto-reload function)
    We should find a better way in the future
    """

    with open("openpype/trigger.py", "w") as f:
        f.write(f"{time.time()}")
