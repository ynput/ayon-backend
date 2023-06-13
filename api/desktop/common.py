import hashlib
import json
import os
from typing import Any, Generator, Literal

import aiofiles
from fastapi import Request
from starlette.responses import FileResponse

from ayon_server.exceptions import AyonException, BadRequestException, NotFoundException
from ayon_server.types import Field, OPModel

Platform = Literal["windows", "linux", "darwin"]


def md5sum(path: str) -> str:
    """Calculate md5sum of file."""

    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_desktop_dir(*args, for_writing: bool = True) -> str:
    """Get path to desktop directory.
    If the directory does not exist, create it.
    args: path to the directory relative to the desktop directory
    """

    # TODO: Make this configurable
    root = "/storage/desktop"
    directory = os.path.join(root, *args)
    if not os.path.isdir(directory):
        if for_writing:
            try:
                os.makedirs(directory)
            except Exception as e:
                raise AyonException(f"Failed to create desktop directory: {e}")
    return directory


def get_desktop_file_path(*args, for_writing: bool = False) -> str:
    subdirs = args[:-1]
    filename = args[-1]
    directory = get_desktop_dir(*subdirs, for_writing=for_writing)
    return os.path.join(directory, filename)


def load_json_file(*args) -> dict[str, Any]:
    path = get_desktop_file_path(*args, for_writing=False)
    if not os.path.isfile(path):
        raise AyonException(f"File does not exist: {path}")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise AyonException(f"Failed to load file {path}: {e}")


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

    directory, filename = os.path.split(target_path)

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
    directory, _filename = os.path.split(path)
    if filename is None:
        filename = _filename
    if not os.path.isfile(path):
        raise NotFoundException(f"No such file {filename}")

    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
    )


class SourceModel(OPModel):
    # For type=server, we do not use absolute url, because base server url can
    # be different for different users. Instead, we provide just the information
    # the source is availabe and the client can construct the url from the
    # filename attribute of BasePackageModel
    # e.g. http://server/api/desktop/{installers|dependency_packages}/{filename}

    type: Literal["server", "url"] = Field(
        ...,
        title="Source type",
        description="If set to server, the file is stored on the server. "
        "If set to url, the file is downloaded from the specified URL.",
        example="url",
    )
    url: str | None = Field(
        None,
        title="Download URL",
        description="URL to download the file from. Only used if type is url",
        example="https://example.com/file.zip",
    )


SOURCES_META = Field(
    default_factory=list,
    title="Sources",
    description="List of sources to download the file from. "
    "Server source is added automatically by the server if the file is uploaded.",
    example=[{"type": "url"}],
)


class BasePackageModel(OPModel):
    filename: str
    platform: Platform
    size: int | None = None
    checksum: str | None = None
    checksum_algorithm: Literal["md5", "sha1", "sha256"] | None = None
    sources: list[SourceModel] = SOURCES_META


class SourcesPatchModel(OPModel):
    sources: list[SourceModel] = SOURCES_META
