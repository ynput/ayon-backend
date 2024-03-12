import os
import signal

from nxtools import logging

from ayon_server.events import dispatch_event
from ayon_server.exceptions import ConstraintViolationException


def restart_server():
    """Force the server to restart.

    This is usually called from ayon_server.api.messaging,
    when `server.restart_requested` event is triggered.
    """
    logging.warning("Server is restarting")

    # Send a SIGHUP to the parent process (gunicorn/granian) to request a reload
    # Gunicorn will restart the server when it receives this signal,
    # but it won't quit itself, so the container will keep running.

    os.kill(os.getppid(), signal.SIGHUP)


async def require_server_restart(
    user_name: str | None = None, description: str | None = None
):
    """Mark the server as requiring a restart.

    This will notify the administrators that the server needs to be restarted.
    When the server is ready to restart, the administrator can use
    restart_server (using /api/system/restart) to trigger server.restart_requested
    event, which (captured by messaging) will trigger restart_server function
    and restart the server.
    """

    topic = "server.restart_requested"
    if description is None:
        description = "Server restart is required"

    try:
        await dispatch_event(topic, hash=topic, description=description, user=user_name)
    except ConstraintViolationException:
        # we don't need to do anything here. If the event fails,
        # it means the event was already triggered, and the server
        # is pending restart.
        pass
