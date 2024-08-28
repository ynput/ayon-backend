def is_image_mime_type(mime_type: str) -> bool:
    mime_type = mime_type.lower()
    return mime_type in [
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/tiff",
        "image/bmp",
        "image/webp",
        "image/ico",
        "image/vnd.adobe.photoshop",
    ]


def is_video_mime_type(mime_type: str) -> bool:
    mime_type = mime_type.lower()
    if mime_type.startswith("video/"):
        return True
    if mime_type == "application/mxf":
        return True
    return False


def print_escaped_bytes(byte_data: bytes):
    decoded_str = byte_data.decode("ascii", "ignore")
    escaped_str = decoded_str.encode("unicode_escape")
    print(escaped_str)


def guess_mime_type(payload: bytes) -> str | None:
    """Guess the MIME type of an image or video from its bytes."""
    if payload[0:4] == b"\x89PNG":
        media_type = "image/png"
    elif payload[0:2] == b"\xff\xd8":
        media_type = "image/jpeg"
    elif payload[0:4] == b"<svg":
        media_type = "image/svg+xml"
    elif payload[0:2] == b"BM":
        media_type = "image/bmp"
    elif payload[0:2] == b"II" or payload[0:2] == b"MM":
        media_type = "image/tiff"
    elif payload[0:4] == b"RIFF" and payload[8:12] == b"WEBP":
        media_type = "image/webp"
    elif payload[0:4] == b"8BPS":
        media_type = "image/vnd.adobe.photoshop"
    elif payload[0:4] == b"GIF8":
        media_type = "image/gif"
    elif payload[0:4] == b"\x00\x00\x01\x00":
        media_type = "image/x-icon"
    elif payload[4:10] == b"ftypqt":
        media_type = "video/quicktime"
    elif payload[4:12] == b"ftypisom":
        media_type = "video/mp4"
    else:
        media_type = None
        bytes_prefix = payload[:16]
        print("Encountered unknown file format with prefix:")
        print_escaped_bytes(bytes_prefix)
    return media_type
