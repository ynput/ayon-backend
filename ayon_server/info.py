import os
import time
from functools import cache
from typing import Any

from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.version import __version__

BOOT_TIME = time.time()


class ReleaseInfo(OPModel):
    version: str = Field(..., title="Backend version", example="1.0.0")
    build_date: str = Field(..., title="Build date", example="20231013")
    build_time: str = Field(..., title="Build time", example="1250")
    frontend_branch: str = Field(..., title="Frontend branch", example="main")
    backend_branch: str = Field(..., title="Backend branch", example="main")
    frontend_commit: str = Field(..., title="Frontend commit", example="1234567")
    backend_commit: str = Field(..., title="Backend commit", example="1234567")


@cache
def get_release_info() -> ReleaseInfo | None:
    """
    Retrieve the release information from the RELEASE file.

    This file is generated during the Docker image build process and contains
    key=value pairs representing various release details.

    Returns:
        ReleaseInfo | None: An instance of ReleaseInfo containing the release
        details if the file is found and successfully parsed. Returns None if
        the file is not found, indicating the server is likely running from a
        mounted local directory.
    """

    if not os.path.isfile("RELEASE"):
        return None

    try:
        release_info: dict[str, Any] = {}
        with open("RELEASE") as f:
            for line in f:
                key, value = line.strip().split("=")
                release_info[key] = value

        return ReleaseInfo(**release_info)
    except Exception:
        with logger.contextualize(nodb=True):
            logger.debug("Failed to load RELEASE file")
        return None


def get_uptime() -> int:
    return int(time.time() - BOOT_TIME)


@cache
def get_version():
    """
    Get the version of the Ayon API
    """

    rel_info = get_release_info()
    build_date = rel_info.build_date if rel_info else None
    build_time = rel_info.build_time if rel_info else None
    version = rel_info.version if rel_info else __version__

    if build_date and build_time:
        version += f"+{build_date}{build_time}"
    else:
        version += "+DEVELOP"
    return version
