__all__ = [
    "get_fake_thumbnail",
    "store_thumbnail",
    "store_project_skeleton_thumbnail",
    "process_thumbnail",
    "calculate_scaled_size",
    "ThumbnailProcessNoop",
]

import base64
import functools

from .process_thumbnail import (
    ThumbnailProcessNoop,
    calculate_scaled_size,
    process_thumbnail,
)
from .store_thumbnail import store_project_skeleton_thumbnail, store_thumbnail


@functools.cache
def get_fake_thumbnail() -> bytes:
    """Returns a fake thumbnail image as a byte stream.

    The image is a 1x1 pixel PNG encoded in base64.
    """
    base64_string = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="  # noqa
    return base64.b64decode(base64_string)
