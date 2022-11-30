import signal
import os

from nxtools import logging


async def restart_server():
    """Force the server to restart."""
    logging.warning("Server is restarting")
    os.kill(os.getpid(), signal.SIGTERM)
