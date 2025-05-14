from pydantic import root_validator

from .rest_model import RestModel

COMMON_FILE_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "zip": "application/zip",
}


class FileInfo(RestModel):
    size: int
    filename: str = "unknown"
    content_type: str = "application/octet-stream"

    @root_validator(pre=True)
    def set_content_type(cls, values):
        if not values.get("content_type"):
            ext = values.get("filename", "").split(".")[-1].lower()
            values["content_type"] = COMMON_FILE_TYPES.get(
                ext,
                "application/octet-stream",
            )
        return values

    def __int__(self) -> int:
        """
        Return the file size as an integer.

        The `size` attribute represents the file size in bytes.
        """
        return self.size
