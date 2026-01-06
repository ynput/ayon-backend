"""
Hot-reload utilities for AYON server.

Allows addons to be loaded without requiring a full server restart
by clearing caches and signaling the server process to reload.
"""

import os
import signal
import subprocess
from typing import Literal

from ayon_server.addons.library import AddonLibrary
from ayon_server.events import EventStream
from ayon_server.logging import logger


async def trigger_hotreload(
    mode: Literal["addon"] = "addon",
    event_id: str | None = None,
) -> bool:
    """
    Trigger a hot-reload of the server without full restart.

    This clears addon caches and signals gunicorn/granian to reload workers.

    Args:
        mode: Type of reload (currently only "addon" is supported)
        event_id: Optional event ID for logging

    Returns:
        True if reload was successful, False otherwise
    """
    try:
        # Clear addon library caches
        await AddonLibrary.clear_addon_list_cache()
        logger.info(
            "Hot-reload: Cleared addon library caches",
            event_id=event_id,
        )

        # Signal the server to reload
        reload_success = _signal_server_reload()

        if reload_success:
            logger.info(
                f"Hot-reload: Server reload signal sent ({mode} mode)",
                event_id=event_id,
            )
        else:
            logger.warning(
                "Hot-reload: Failed to signal server, attempting via script",
                event_id=event_id,
            )
            reload_success = _reload_via_script()

        return reload_success

    except Exception as err:
        logger.error(
            f"Hot-reload: Error during reload: {err}",
            event_id=event_id,
            exc_info=True,
        )
        return False


def _signal_server_reload() -> bool:
    """
    Signal the server process to reload (SIGHUP for gunicorn/granian).

    Returns:
        True if signal was sent successfully
    """
    server_type = os.getenv("AYON_SERVER_TYPE", "gunicorn")

    try:
        # Find the process ID
        ps_output = subprocess.check_output(
            ["ps", "aux"],
            text=True,
            timeout=5,
        )

        pid = None
        for line in ps_output.split("\n"):
            if server_type in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pid = int(parts[1])
                        break
                    except (ValueError, IndexError):
                        continue

        if pid is None:
            logger.warning(
                f"Hot-reload: Could not find {server_type} process",
            )
            return False

        # Send SIGHUP to reload workers
        os.kill(pid, signal.SIGHUP)
        logger.info(f"Hot-reload: Sent SIGHUP to process {pid}")
        return True

    except Exception as err:
        logger.warning(f"Hot-reload: Failed to signal via SIGHUP: {err}")
        return False


def _reload_via_script() -> bool:
    """
    Attempt to reload via the reload.sh script.

    Returns:
        True if script executed successfully
    """
    try:
        # Try to find and run reload.sh
        reload_script = "/workspace/reload.sh"
        if not os.path.exists(reload_script):
            reload_script = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "reload.sh",
            )

        if os.path.exists(reload_script):
            subprocess.run(
                ["bash", reload_script],
                timeout=10,
                check=False,
            )
            return True

    except Exception as err:
        logger.warning(f"Hot-reload: Failed to run reload script: {err}")

    return False


async def notify_clients_addon_reload(
    event_id: str | None = None,
) -> None:
    """
    Notify connected clients that addons have been reloaded.

    This sends a broadcast message via the event system
    so clients can refresh their addon list.

    Args:
        event_id: Optional event ID for logging context
    """
    try:
        await EventStream.dispatch(
            "server.addons_changed",
            description="Addons have been reloaded",
            summary={"reloaded_at": None},  # Will be auto-filled with timestamp
            finished=True,
        )
        logger.info(
            "Hot-reload: Notified clients of addon changes",
            event_id=event_id,
        )
    except Exception as err:
        logger.warning(
            f"Hot-reload: Failed to notify clients: {err}",
            event_id=event_id,
        )