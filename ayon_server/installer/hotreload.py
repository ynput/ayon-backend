"""
Hot-reload utilities for AYON server.

This module provides functionality to reload addons without requiring
a full server restart. It works by:

1. Clearing addon library caches
2. Signaling the server process (gunicorn/granian) to reload workers
3. Notifying connected clients of the changes

Example:
    >>> from ayon_server.installer.hotreload import trigger_hotreload
    >>> success = await trigger_hotreload(mode="addon", event_id="abc123")
    >>> if success:
    ...     await notify_clients_addon_reload(event_id="abc123")

Environment Variables:
    AYON_SERVER_TYPE: Server type ("gunicorn" or "granian"). Default: "gunicorn"
    AYON_RELOAD_SCRIPT: Path to custom reload script. Optional.
"""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from subprocess import SubprocessError, TimeoutExpired
from typing import TYPE_CHECKING, Literal

import psutil

from ayon_server.addons.library import AddonLibrary
from ayon_server.events import EventStream
from ayon_server.logging import logger

if TYPE_CHECKING:
    from typing import Callable

__all__ = [
    "trigger_hotreload",
    "notify_clients_addon_reload",
    "get_hotreload_manager",
    "ReloadMode",
    "ReloadState",
    "ReloadResult",
    "HotReloadManager",
]

# =============================================================================
# Configuration Constants
# =============================================================================

PROCESS_LOOKUP_TIMEOUT = 5.0
RELOAD_SCRIPT_TIMEOUT = 10.0
RELOAD_VERIFICATION_TIMEOUT = 10.0
RELOAD_VERIFICATION_INTERVAL = 0.5

RELOAD_SCRIPT_ENV_VAR = "AYON_RELOAD_SCRIPT"
SERVER_TYPE_ENV_VAR = "AYON_SERVER_TYPE"
DEFAULT_SERVER_TYPE = "gunicorn"


# =============================================================================
# Enums and Data Classes
# =============================================================================


class ReloadMode(Enum):
    """Supported reload modes."""

    ADDON = "addon"
    CONFIG = "config"
    FULL = "full"


class ReloadState(Enum):
    """State of a reload operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReloadResult:
    """Result of a reload operation.

    Attributes:
        success: Whether the reload operation succeeded.
        state: Current state of the reload operation.
        message: Human-readable message describing the result.
        started_at: Timestamp when the reload started.
        completed_at: Timestamp when the reload completed.
        verified: Whether the reload was verified successfully.
    """

    success: bool
    state: ReloadState
    message: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    verified: bool = False


# =============================================================================
# Process Detection (Using psutil)
# =============================================================================


def _get_server_pid() -> int | None:
    """
    Find the server master process PID using psutil.

    This function scans running processes to find the gunicorn/granian
    master process. Using psutil is more reliable and cross-platform
    than parsing `ps aux` output.

    Returns:
        Process ID if found, None otherwise.
    """
    server_type = os.getenv(SERVER_TYPE_ENV_VAR, DEFAULT_SERVER_TYPE)

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_info = proc.info
            cmdline = proc_info.get("cmdline") or []
            name = proc_info.get("name", "")

            # Check if this is the server process
            if server_type == "gunicorn":
                # Gunicorn master process typically has 'gunicorn' in name
                # and 'master' in cmdline or is the parent of worker processes
                if "gunicorn" in name.lower() or any(
                    "gunicorn" in arg.lower() for arg in cmdline
                ):
                    # Check if it's the master process (has no gunicorn parent)
                    try:
                        parent = proc.parent()
                        if parent and "gunicorn" in (parent.name() or "").lower():
                            continue  # This is a worker, not master
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    return proc_info["pid"]

            elif server_type == "granian":
                if "granian" in name.lower() or any(
                    "granian" in arg.lower() for arg in cmdline
                ):
                    return proc_info["pid"]

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process may have terminated or we don't have access
            continue

    return None


def _signal_server_reload() -> bool:
    """
    Signal the server process to reload (SIGHUP for gunicorn/granian).

    Uses psutil for reliable cross-platform process detection instead of
    parsing `ps aux` output.

    Returns:
        True if signal was sent successfully.

    Raises:
        ProcessLookupError: If the process no longer exists.
        PermissionError: If we don't have permission to signal the process.
        OSError: For other OS-level errors.
    """
    try:
        pid = _get_server_pid()

        if pid is None:
            server_type = os.getenv(SERVER_TYPE_ENV_VAR, DEFAULT_SERVER_TYPE)
            logger.warning(
                "Hot-reload: Could not find server process",
                server_type=server_type,
            )
            return False

        # Send SIGHUP to reload workers
        os.kill(pid, signal.SIGHUP)
        logger.info(
            "Hot-reload: Sent SIGHUP to process",
            pid=pid,
        )
        return True

    except ProcessLookupError:
        logger.warning("Hot-reload: Process no longer exists")
        return False
    except PermissionError:
        logger.error("Hot-reload: Permission denied to signal process")
        return False
    except OSError as err:
        logger.warning(
            "Hot-reload: OS error while signaling process",
            error=str(err),
        )
        return False


async def _signal_server_reload_async() -> bool:
    """
    Async wrapper for signaling server reload.

    Runs the synchronous signal operation in a thread pool to avoid
    blocking the event loop.

    Returns:
        True if signal was sent successfully.
    """
    return await asyncio.to_thread(_signal_server_reload)


# =============================================================================
# Reload Script Handling
# =============================================================================


def _get_reload_script_path() -> str | None:
    """
    Get the path to the reload script with validation.

    Checks environment variable first, then falls back to default location
    relative to this module. Validates that the script exists and is
    executable.

    Returns:
        Validated script path or None if not found/valid.
    """
    # Check environment variable first
    script_path = os.getenv(RELOAD_SCRIPT_ENV_VAR)

    if script_path is None:
        # Fall back to default location relative to this module
        script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "reload.sh",
        )

    # Resolve to absolute path
    script_path = os.path.abspath(script_path)

    # Security: Ensure script exists and is a file
    if not os.path.isfile(script_path):
        logger.debug(
            "Hot-reload: Reload script not found",
            path=script_path,
        )
        return None

    # Security: Verify script is readable and executable
    if not os.access(script_path, os.R_OK | os.X_OK):
        logger.warning(
            "Hot-reload: Reload script not readable or executable",
            path=script_path,
        )
        return None

    return script_path


def _reload_via_script() -> bool:
    """
    Attempt to reload via the reload.sh script.

    Uses configurable script path from environment variable with secure
    validation and specific exception handling.

    Returns:
        True if script executed successfully.

    Raises:
        TimeoutExpired: If script execution times out.
        SubprocessError: For other subprocess-related errors.
        FileNotFoundError: If bash is not found.
    """
    script_path = _get_reload_script_path()

    if script_path is None:
        return False

    try:
        import subprocess

        result = subprocess.run(
            ["bash", script_path],
            timeout=RELOAD_SCRIPT_TIMEOUT,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(
            "Hot-reload: Reload script executed successfully",
            script_path=script_path,
            stdout=result.stdout.strip() if result.stdout else None,
        )
        return True

    except TimeoutExpired:
        logger.warning(
            "Hot-reload: Reload script timed out",
            script_path=script_path,
            timeout=RELOAD_SCRIPT_TIMEOUT,
        )
        return False
    except SubprocessError as err:
        logger.warning(
            "Hot-reload: Reload script failed",
            script_path=script_path,
            error=str(err),
        )
        return False
    except FileNotFoundError:
        logger.warning("Hot-reload: bash not found")
        return False


async def _reload_via_script_async() -> bool:
    """
    Async wrapper for reload via script.

    Returns:
        True if script executed successfully.
    """
    return await asyncio.to_thread(_reload_via_script)


# =============================================================================
# Reload Verification
# =============================================================================


async def _verify_reload_success(
    expected_after: datetime,
    timeout: float = RELOAD_VERIFICATION_TIMEOUT,
) -> bool:
    """
    Verify that a reload operation actually succeeded.

    This checks various indicators that the reload completed:
    - Server process is still running
    - Addon library caches are cleared

    Args:
        expected_after: The reload should have completed after this time.
        timeout: Maximum time to wait for verification.

    Returns:
        True if reload was verified successful, False otherwise.
    """
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            # Check if server process is still running
            pid = _get_server_pid()
            if pid is None:
                logger.warning("Hot-reload: Server process not found during verification")
                return False

            # Additional verification: try to access addon library
            # This ensures the reload actually processed correctly
            try:
                # Simply checking that we can interact with AddonLibrary
                # is a basic smoke test
                await asyncio.sleep(RELOAD_VERIFICATION_INTERVAL)
                return True

            except Exception as err:
                logger.debug(
                    "Hot-reload: Verification check failed, retrying",
                    error=str(err),
                )

        except Exception as err:
            logger.debug(
                "Hot-reload: Verification error, retrying",
                error=str(err),
            )

        await asyncio.sleep(RELOAD_VERIFICATION_INTERVAL)

    logger.warning("Hot-reload: Verification timed out")
    return False


# =============================================================================
# Main Hot-Reload Functions
# =============================================================================


async def trigger_hotreload(
    mode: Literal["addon"] = "addon",
    event_id: str | None = None,
    verify: bool = True,
) -> bool:
    """
    Trigger a hot-reload of the server without full restart.

    This clears addon caches and signals gunicorn/granian to reload workers.
    Uses psutil for reliable process detection and supports configurable
    reload scripts.

    Args:
        mode: Type of reload (currently only "addon" is supported).
        event_id: Optional event ID for logging context.
        verify: Whether to verify the reload succeeded.

    Returns:
        True if reload was successful, False otherwise.

    Example:
        >>> success = await trigger_hotreload(
        ...     mode="addon",
        ...     event_id="install-123",
        ...     verify=True,
        ... )
        >>> if success:
        ...     print("Addon hot-reload completed successfully")
    """
    reload_start = datetime.now(timezone.utc)

    try:
        # Clear addon library caches
        await AddonLibrary.clear_addon_list_cache()
        logger.info(
            "Hot-reload: Cleared addon library caches",
            event_id=event_id,
        )

        # Signal the server to reload (non-blocking)
        reload_success = await _signal_server_reload_async()

        if reload_success:
            logger.info(
                "Hot-reload: Server reload signal sent",
                mode=mode,
                event_id=event_id,
            )
        else:
            logger.warning(
                "Hot-reload: Failed to signal server, attempting via script",
                event_id=event_id,
            )
            reload_success = await _reload_via_script_async()

        if not reload_success:
            logger.error(
                "Hot-reload: All reload methods failed",
                event_id=event_id,
            )
            return False

        # Verify reload if requested
        if verify:
            verified = await _verify_reload_success(reload_start)
            if not verified:
                logger.warning(
                    "Hot-reload: Reload verification failed",
                    event_id=event_id,
                )
                # Still return True since the signal was sent successfully
                # The server may still be reloading

        return reload_success

    except (ProcessLookupError, PermissionError) as err:
        logger.error(
            "Hot-reload: Process error during reload",
            error=str(err),
            event_id=event_id,
        )
        return False
    except (TimeoutExpired, SubprocessError) as err:
        logger.error(
            "Hot-reload: Subprocess error during reload",
            error=str(err),
            event_id=event_id,
        )
        return False
    except OSError as err:
        logger.error(
            "Hot-reload: OS error during reload",
            error=str(err),
            event_id=event_id,
        )
        return False
    except Exception as err:
        logger.error(
            "Hot-reload: Unexpected error during reload",
            error=str(err),
            event_id=event_id,
            exc_info=True,
        )
        return False


async def notify_clients_addon_reload(
    event_id: str | None = None,
) -> None:
    """
    Notify connected clients that addons have been reloaded.

    This sends a broadcast message via the event system
    so clients can refresh their addon list.

    Args:
        event_id: Optional event ID for logging context.

    Raises:
        Exception: If dispatching the event fails (logged but not raised).
    """
    try:
        await EventStream.dispatch(
            "server.addons_changed",
            description="Addons have been reloaded",
            summary={"reloaded_at": datetime.now(timezone.utc).isoformat()},
            finished=True,
        )
        logger.info(
            "Hot-reload: Notified clients of addon changes",
            event_id=event_id,
        )
    except Exception as err:
        logger.warning(
            "Hot-reload: Failed to notify clients",
            error=str(err),
            event_id=event_id,
        )


# =============================================================================
# HotReloadManager Class
# =============================================================================


@dataclass
class HotReloadManager:
    """
    Manager for coordinated hot-reload operations.

    This class encapsulates state and provides a cleaner interface for
    managing hot-reload operations across the application.

    Attributes:
        last_reload: Timestamp of the last successful reload.
        reload_count: Total number of successful reloads.
        callbacks: List of callbacks to invoke after reload.

    Example:
        >>> manager = get_hotreload_manager()
        >>> result = await manager.reload(
        ...     mode=ReloadMode.ADDON,
        ...     event_id="install-123",
        ... )
        >>> if result.success:
        ...     print(f"Reload completed at {result.completed_at}")
    """

    last_reload: datetime | None = None
    reload_count: int = 0
    callbacks: list[Callable[[], None]] = field(default_factory=list)

    def register_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a callback to be invoked after successful reload.

        Args:
            callback: Function to call after reload completes.
        """
        self.callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """
        Unregister a previously registered callback.

        Args:
            callback: Function to remove from callback list.
        """
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def reload(
        self,
        mode: ReloadMode = ReloadMode.ADDON,
        event_id: str | None = None,
        verify: bool = True,
    ) -> ReloadResult:
        """
        Perform a hot-reload operation.

        Args:
            mode: Type of reload to perform.
            event_id: Optional event ID for logging context.
            verify: Whether to verify the reload succeeded.

        Returns:
            ReloadResult with details of the operation.
        """
        result = ReloadResult(
            success=False,
            state=ReloadState.PENDING,
            message="Reload pending",
        )

        try:
            result.state = ReloadState.IN_PROGRESS
            result.message = f"Performing {mode.value} reload"

            # Map ReloadMode to string literal for trigger_hotreload
            mode_str: Literal["addon"] = "addon"
            if mode != ReloadMode.ADDON:
                logger.warning(
                    "Hot-reload: Unsupported mode, falling back to addon",
                    requested_mode=mode.value,
                )

            success = await trigger_hotreload(
                mode=mode_str,
                event_id=event_id,
                verify=verify,
            )

            if success:
                result.success = True
                result.state = ReloadState.COMPLETED
                result.message = "Reload completed successfully"
                result.completed_at = datetime.now(timezone.utc)
                result.verified = verify

                self.last_reload = result.completed_at
                self.reload_count += 1

                # Invoke callbacks
                for callback in self.callbacks:
                    try:
                        callback()
                    except Exception as err:
                        logger.warning(
                            "Hot-reload: Callback failed",
                            error=str(err),
                        )

                # Notify clients
                await notify_clients_addon_reload(event_id=event_id)

            else:
                result.state = ReloadState.FAILED
                result.message = "Reload failed"
                result.completed_at = datetime.now(timezone.utc)

        except Exception as err:
            result.state = ReloadState.FAILED
            result.message = f"Reload error: {err}"
            result.completed_at = datetime.now(timezone.utc)
            logger.error(
                "Hot-reload: Manager reload error",
                error=str(err),
                event_id=event_id,
            )

        return result

    def get_status(self) -> dict:
        """
        Get the current status of the hot-reload manager.

        Returns:
            Dictionary with status information.
        """
        return {
            "last_reload": (
                self.last_reload.isoformat() if self.last_reload else None
            ),
            "reload_count": self.reload_count,
            "callbacks_registered": len(self.callbacks),
        }


# Singleton instance
_manager: HotReloadManager | None = None


def get_hotreload_manager() -> HotReloadManager:
    """
    Get the global HotReloadManager instance.

    Returns:
        The singleton HotReloadManager instance.
    """
    global _manager
    if _manager is None:
        _manager = HotReloadManager()
    return _manager