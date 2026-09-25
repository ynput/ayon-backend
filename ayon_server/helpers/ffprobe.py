import asyncio
import json
from typing import Any, Literal

ReviewableAvailability = Literal[
    "unknown", "conversionRequired", "conversionRecommended", "ready"
]


async def ffprobe(file_path: str) -> dict[str, Any]:
    """Runs ffprobe on a file and returns the metadata."""
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(f"ffprobe failed: {stderr.decode()}")

    return json.loads(stdout)


async def extract_media_info(file_path: str) -> dict[str, Any]:
    """Extracts metadata from a video file."""

    try:
        probe_data = await ffprobe(file_path)
    except Exception:
        return {}

    result: dict[str, Any] = {
        "probeVersion": 1,
        "majorBrand": probe_data.get("format", {})
        .get("tags", {})
        .get("major_brand", "")
        .strip(),
    }

    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            fps_str = stream.get("r_frame_rate")
            fps_parts = fps_str.split("/")
            if len(fps_parts) == 2:
                fps = int(fps_parts[0]) / int(fps_parts[1])
            else:
                fps = float(fps_parts[0])

            result.update(
                {
                    "videoTrackIndex": stream.get("index"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "pixelFormat": stream.get("pix_fmt"),
                    "frameRate": fps,
                    "duration": float(stream.get("duration", 0)),
                    "codec": stream.get("codec_name"),
                    "iframeOnly": stream.get("has_b_frames", 1) == 0,
                }
            )

        elif stream.get("codec_type") == "audio":
            if "audioTracks" not in result:
                result["audioTracks"] = []
            result["audioTracks"].append(
                {
                    "index": stream.get("index"),
                    "codec": stream.get("codec_name"),
                    "sampleRate": stream.get("sample_rate"),
                    "channels": stream.get("channels"),
                }
            )

    return result


def availability_from_media_info(mediainfo: dict[str, Any]) -> ReviewableAvailability:
    duration = mediainfo.get("duration", 0)
    codec = mediainfo.get("codec", "unknown")
    major_brand = mediainfo.get("majorBrand", "unknown") or "unknown"
    major_brand = major_brand.strip()

    if mediainfo.get("videoTrackIndex") is None:
        # no video track. weird.
        return "unknown"

    if duration == 0:
        # images
        if codec in ["mjpeg", "png", "webp"]:
            return "ready"
        else:
            return "conversionRequired"

    # video files

    if codec not in ["h264", "vp9"]:
        return "conversionRequired"

    if major_brand not in ["mp42", "isom"]:
        if major_brand in ["qt"]:
            return "conversionRecommended"
        if major_brand == "unknown":
            # hack for earlier versions of ayon
            # we will assume that the file is an mp4
            # because we don't have the major brand info
            # (but we already know it's a compatible codec)
            pass
        else:
            return "conversionRequired"

    # apart from firefox, all browsers support almost all pixel formats
    # if mediainfo.get("pixelFormat") not in ["yuv420p", "yuv444p"]:
    #     return "conversionRecommended"

    if not mediainfo.get("iframeOnly"):
        return "conversionRecommended"

    return "ready"
