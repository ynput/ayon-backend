import hashlib
import json
import os
from typing import Any, Generator

import aiofiles
from fastapi import Request
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException
from ayon_server.installer.common import get_desktop_dir
from ayon_server.types import Field, OPModel


def md5sum(path: str) -> str:
    """Calculate md5sum of file."""

    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_desktop_file_path(*args, for_writing: bool = False) -> str:
    subdirs = args[:-1]
    filename = args[-1]
    directory = get_desktop_dir(*subdirs, for_writing=for_writing)
    return os.path.join(directory, filename)


def load_json_file(*args) -> dict[str, Any]:
    path = get_desktop_file_path(*args, for_writing=False)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File does not exist: {path}")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to load file {path}: {e}")


def save_json_file(*args, data: Any) -> None:
    path = get_desktop_file_path(*args, for_writing=True)
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        raise AyonException(f"Failed to save file {path}: {e}")


def iter_names(directory: str) -> Generator[str, None, None]:
    """Iterate over package names in a directory."""

    root = get_desktop_dir(directory, for_writing=False)
    if not os.path.isdir(root):
        return
    for filename in os.listdir(root):
        if not os.path.isfile(os.path.join(root, filename)):
            continue
        if not filename.endswith(".json"):
            continue
        yield filename[:-5]


async def handle_upload(request: Request, target_path: str) -> None:
    """Store raw body from the request to a file."""

    directory, _ = os.path.split(target_path)

    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            raise AyonException(f"Failed to create directory: {e}") from e

    i = 0
    async with aiofiles.open(target_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)
            i += len(chunk)

    if i == 0:
        raise BadRequestException("Empty file")

    return None


async def handle_download(
    path: str,
    media_type: str = "application/octet-stream",
    filename: str | None = None,
) -> FileResponse:
    _, _filename = os.path.split(path)
    if filename is None:
        filename = _filename
    if not os.path.isfile(path):
        raise NotFoundException(f"No such file {filename}")

    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
    )


class InstallResponseModel(OPModel):
    event_id: str | None = Field(None, title="Event ID")
