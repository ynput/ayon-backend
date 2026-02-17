__all__ = [
    "get_desktop_dir",
    "md5sum",
    "get_desktop_file_path",
    "load_json_file",
    "save_json_file",
    "iter_names",
    "InstallResponseModel",
    "FileNameInPath",
]

import hashlib
import json
import os
from typing import Annotated, Any

from fastapi import Path

from ayon_server.exceptions import AyonException
from ayon_server.installer.common import get_desktop_dir, iter_names
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
        with open(path) as f:
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


class InstallResponseModel(OPModel):
    event_id: str | None = Field(None, title="Event ID")


FileNameInPath = Annotated[str, Path(title="File name", regex=r"^[\w\-. ]+$")]
