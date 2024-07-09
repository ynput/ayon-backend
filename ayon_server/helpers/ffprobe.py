import asyncio
import json
from typing import Any


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
