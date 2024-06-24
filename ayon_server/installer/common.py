import os

from ayon_server.exceptions import AyonException


def get_desktop_dir(*args: str, for_writing: bool = True) -> str:
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
