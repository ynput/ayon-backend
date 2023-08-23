import os
import uuid

import httpx

from ayon_server.exceptions import AyonException


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


def download_file(url: str, target_path: str) -> None:
    """Downloads a file from a url to a target path"""
    temp_file_path = target_path + f".{uuid.uuid1().hex}.part"
    with httpx.stream("GET", url) as response:
        response.raise_for_status()
        with open(temp_file_path, "wb") as temp_file:
            for chunk in response.iter_bytes():
                temp_file.write(chunk)
    os.rename(temp_file_path, target_path)
