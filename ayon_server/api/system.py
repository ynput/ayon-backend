import os
import signal

from nxtools import logging


def restart_server():
    """Force the server to restart."""
    logging.warning("Server is restarting")

    # Send a SIGHUP to the parent process (gunicorn) to request a reload
    # Gunicorn will restart the server when it receives this signal,
    # but it won't quit itself, so the container will keep running.

    os.kill(os.getppid(), signal.SIGHUP)
