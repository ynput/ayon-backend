import os
import signal

from nxtools import logging


def restart_server():
    """Force the server to restart."""
    logging.warning("Server is restarting")
    os.kill(os.getppid(), signal.SIGTERM)
