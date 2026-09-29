"""Filmstrips - hover-scrub previews of video files.

A filmstrip is a single AVIF image containing `frames` frames of a video,
laid out in a grid of `columns` columns, left to right, top to bottom.
Regardless of the video length, frame `i` is taken from the middle of
the i-th of `frames` equally long segments of the video, so clients can map
a relative cursor position over a thumbnail directly to a frame:
`index = floor(x / width * frames)`.

Filmstrips are generated lazily (on the first request) or eagerly when
a video reviewable is uploaded, stored in the project storage under the
ID of the source file, and described in the `filmstrip` key of the file
record data.
"""

import asyncio
import io
import math
import os
from typing import Any, NamedTuple, TypedDict, TypeGuard

import aiofiles
import aiofiles.tempfile
from fastapi import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.exceptions import AyonException, NotFoundException
from ayon_server.files import Storages
from ayon_server.helpers.ffprobe import ffprobe
from ayon_server.helpers.mimetypes import is_video_mime_type
from ayon_server.helpers.thumbnails.thumbnail_acl import ensure_accessible
from ayon_server.helpers.thumbnails.thumbnail_info_resolvers import (
    resolve_folder_thumbnail_info,
    resolve_task_thumbnail_info,
    resolve_version_thumbnail_info,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.utils.request_coalescer import RequestCoalescer

# Max number of filmstrips generated at the same time
FILMSTRIP_SEMAPHORE = asyncio.Semaphore(2)

# Videos up to this many frames are decoded in a single pass, which is much
# faster than seeking for short, long-GOP clips. Longer videos are sampled
# by seeking to each frame in parallel processes.
SINGLE_PASS_MAX_FRAMES = 1500

# Max number of ffmpeg processes extracting frames for a single filmstrip
FRAME_CONCURRENCY = 4

# Max time to extract frames (seconds)
FRAME_TIMEOUT = 30
SINGLE_PASS_TIMEOUT = 120

FILMSTRIP_CACHE_TTL = 600
FAILURE_CACHE_TTL = 3600

# Bump when the image layout or encoding changes to regenerate stored filmstrips
FILMSTRIP_VERSION = 1

# AVIF is about half the size of JPEG at the same visual quality. Settings were
# picked with SSIMULACRA2 on animated and grainy live-action footage: 4:4:4
# keeps coloured edges clean and costs less than raising the quality,
# speed 7 encodes 2.3x faster than 6 for ~1% larger files, higher speeds grow
# the file considerably.
# With the default 480px frames, a filmstrip is ~150-270kB and looks close
# to lossless on ~240px wide cards on 2x displays.
FILMSTRIP_MIME = "image/avif"
AVIF_QUALITY = 60
AVIF_SPEED = 7


class FilmstripInfo(TypedDict):
    version: int
    mime: str
    frames: int
    columns: int
    frameWidth: int
    frameHeight: int
    frameSize: int  # max frame size the filmstrip was created with


class Filmstrip(NamedTuple):
    file_id: str
    content: bytes
    info: FilmstripInfo


#
# Generation
#


def _ffmpeg_base_args() -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
    ]


def _output_args(frame_size: int, stream_index: int | None, vf: str = "") -> list[str]:
    # Fit the frame into frame_size x frame_size box, never upscale
    scale_filter = (
        f"scale='min(iw,{frame_size})':'min(ih,{frame_size})'"
        ":force_original_aspect_ratio=decrease:flags=lanczos"
    )
    args = []
    if stream_index is not None:
        args.extend(["-map", f"0:{stream_index}"])
    args.extend(["-vf", f"{vf},{scale_filter}" if vf else scale_filter])
    return args


async def _run_ffmpeg(cmd: list[str], timeout: float) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise

    if proc.returncode != 0:
        raise AyonException(f"ffmpeg failed: {stderr.decode()[-500:]}")
    return stdout


async def _extract_frames_single_pass(
    video_path: str,
    *,
    duration: float,
    frames: int,
    frame_size: int,
    stream_index: int | None = None,
) -> list[bytes | None]:
    """Decode the whole video once and pick the first frame of each segment
    after its middle. Returns BMP bytes for each of `frames` samples."""

    select_filter = (
        f"select='gte(t-start_t\\,(selected_n+0.5)*{duration:.6f}/{frames})'"
    )
    async with aiofiles.tempfile.TemporaryDirectory() as temp_dir:
        cmd = _ffmpeg_base_args()
        cmd.extend(["-i", video_path])
        cmd.extend(_output_args(frame_size, stream_index, select_filter))
        cmd.extend(
            [
                "-fps_mode",
                "passthrough",
                "-frames:v",
                str(frames),
                # uncompressed, PNG encoding takes ~20% of the extraction time
                "-c:v",
                "bmp",
                os.path.join(temp_dir, "%03d.bmp"),
            ]
        )
        await _run_ffmpeg(cmd, SINGLE_PASS_TIMEOUT)

        results: list[bytes | None] = []
        for i in range(frames):
            try:
                async with aiofiles.open(
                    os.path.join(temp_dir, f"{i + 1:03d}.bmp"), "rb"
                ) as f:
                    results.append(await f.read())
            except FileNotFoundError:
                results.append(None)
        return results


async def _extract_frame(
    video_path: str,
    timestamp: float,
    *,
    frame_size: int,
    stream_index: int | None = None,
) -> bytes | None:
    """Extract a single, downscaled frame from a video as BMP bytes.

    Returns None if there is no frame at the given timestamp.
    """

    cmd = _ffmpeg_base_args()
    cmd.extend(
        [
            # Frames are extracted in parallel processes,
            # don't oversubscribe the CPU
            "-threads",
            "1",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            video_path,
        ]
    )
    cmd.extend(_output_args(frame_size, stream_index))
    cmd.extend(["-frames:v", "1", "-f", "image2pipe", "-c:v", "bmp", "-"])
    return await _run_ffmpeg(cmd, FRAME_TIMEOUT) or None


async def _extract_frames_by_seeking(
    video_path: str,
    *,
    duration: float,
    frames: int,
    frame_size: int,
    stream_index: int | None = None,
) -> list[bytes | None]:
    """Seek to the middle of each segment. Returns BMP bytes for each sample."""

    frame_semaphore = asyncio.Semaphore(FRAME_CONCURRENCY)

    async def extract(index: int) -> bytes | None:
        timestamp = (index + 0.5) * duration / frames
        async with frame_semaphore:
            try:
                return await _extract_frame(
                    video_path,
                    timestamp,
                    frame_size=frame_size,
                    stream_index=stream_index,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Unable to extract filmstrip frame at {timestamp}: {e}")
                return None

    return await asyncio.gather(*(extract(i) for i in range(frames)))


def get_filmstrip_columns(frames: int) -> int:
    """Number of grid columns, keeping the image close to the frame aspect"""
    return math.ceil(math.sqrt(frames))


def _compose_filmstrip(frames: list[bytes], columns: int) -> tuple[bytes, int, int]:
    """Place frames in a grid and return (avif, frame_w, frame_h)"""

    images = [Image.open(io.BytesIO(frame)).convert("RGB") for frame in frames]
    frame_width, frame_height = images[0].size
    rows = math.ceil(len(images) / columns)
    grid = Image.new("RGB", (frame_width * columns, frame_height * rows))
    for i, image in enumerate(images):
        if image.size != (frame_width, frame_height):
            # The resolution may change mid-stream
            image = image.resize((frame_width, frame_height), Image.LANCZOS)  # type: ignore
        grid.paste(image, ((i % columns) * frame_width, (i // columns) * frame_height))

    buffer = io.BytesIO()
    grid.save(
        buffer,
        format="AVIF",
        quality=AVIF_QUALITY,
        speed=AVIF_SPEED,
        subsampling="4:4:4",
    )
    return buffer.getvalue(), frame_width, frame_height


async def create_filmstrip(
    video_path: str,
    *,
    duration: float,
    frames: int,
    frame_size: int,
    stream_index: int | None = None,
    frame_rate: float | None = None,
) -> tuple[bytes, FilmstripInfo]:
    """Create a filmstrip image from a video file (path or URL)."""

    if duration <= 0:
        raise AyonException("Cannot create a filmstrip of a video without duration")

    kwargs: dict[str, Any] = {
        "duration": duration,
        "frames": frames,
        "frame_size": frame_size,
        "stream_index": stream_index,
    }

    results: list[bytes | None] = []
    async with FILMSTRIP_SEMAPHORE:
        if duration * (frame_rate or 25) <= SINGLE_PASS_MAX_FRAMES:
            try:
                results = await _extract_frames_single_pass(video_path, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Single pass filmstrip extraction failed: {e}")

        if not any(results):
            results = await _extract_frames_by_seeking(video_path, **kwargs)

    # There may be no frame at the end of some files (or of an inaccurate duration).
    # Fill the gaps with the nearest preceding frame (or the first one found)

    first_found = next((r for r in results if r), None)
    if first_found is None:
        raise AyonException("Unable to extract any frame")

    filled: list[bytes] = []
    last = first_found
    for result in results:
        if result:
            last = result
        filled.append(last)

    columns = get_filmstrip_columns(frames)
    payload, frame_width, frame_height = await run_in_threadpool(
        _compose_filmstrip, filled, columns
    )
    info: FilmstripInfo = {
        "version": FILMSTRIP_VERSION,
        "mime": FILMSTRIP_MIME,
        "frames": frames,
        "columns": columns,
        "frameWidth": frame_width,
        "frameHeight": frame_height,
        "frameSize": frame_size,
    }
    return payload, info


#
# File filmstrips
#


def _is_current(info: Any) -> TypeGuard[FilmstripInfo]:
    """Check whether stored filmstrip info matches the current configuration"""
    if not info:
        return False
    return (
        info.get("version") == FILMSTRIP_VERSION
        and info.get("frames") == ayonconfig.filmstrip_frames
        and info.get("frameSize") == ayonconfig.filmstrip_frame_size
    )


async def _generate_file_filmstrip(
    project_name: str,
    file_id: str,
    mime: str,
    media_info: dict[str, Any],
) -> Filmstrip:
    storage = await Storages.project(project_name)
    if storage.storage_type == "local":
        path = await storage.get_path(file_id)
        if not os.path.isfile(path):
            raise NotFoundException("Source file of the filmstrip not found")
    elif storage.storage_type == "s3":
        path = await storage.get_signed_url(file_id)
    else:
        raise AyonException("Unsupported storage type. This should not happen")

    duration = float(media_info.get("duration") or 0)
    if duration <= 0:
        # Stream duration is not always available (e.g. mkv, webm)
        probe = await ffprobe(path)
        duration = float(probe.get("format", {}).get("duration") or 0)

    logger.debug(f"Creating filmstrip of {project_name}/{file_id}")
    payload, info = await create_filmstrip(
        path,
        duration=duration,
        frames=ayonconfig.filmstrip_frames,
        frame_size=ayonconfig.filmstrip_frame_size,
        stream_index=media_info.get("videoTrackIndex"),
        frame_rate=media_info.get("frameRate"),
    )

    await storage.store_filmstrip(file_id, payload)
    await Postgres.execute(
        f"""
        UPDATE project_{project_name}.files
        SET data = data || $2::jsonb
        WHERE id = $1
        """,
        file_id,
        {"filmstrip": info},
    )
    await Redis.set(
        "filmstrip", f"{project_name}:{file_id}", payload, ttl=FILMSTRIP_CACHE_TTL
    )
    return Filmstrip(file_id=file_id, content=payload, info=info)


async def get_file_filmstrip(project_name: str, file_id: str) -> Filmstrip:
    """Return the filmstrip of a video file, creating it if needed.

    Raises NotFoundException if the file does not exist or
    a filmstrip cannot be created for it (not a video, broken file...)
    """

    file_id = file_id.replace("-", "")
    cache_key = f"{project_name}:{file_id}"

    row = await Postgres.fetchrow(
        f"SELECT data FROM project_{project_name}.files WHERE id = $1",
        file_id,
    )
    if not row:
        raise NotFoundException("File not found")

    data = row["data"] or {}
    mime = data.get("mime", "application/octet-stream")
    media_info = data.get("mediaInfo") or {}
    info = data.get("filmstrip")

    if not is_video_mime_type(mime):
        raise NotFoundException(f"Filmstrips are not available for {mime} files")

    if media_info and media_info.get("videoTrackIndex") is None:
        raise NotFoundException("File has no video track")

    if _is_current(info):
        content = await Redis.get("filmstrip", cache_key)
        if content is None:
            storage = await Storages.project(project_name)
            try:
                content = await storage.get_filmstrip(file_id)
            except FileNotFoundError:
                pass
            else:
                await Redis.set(
                    "filmstrip", cache_key, content, ttl=FILMSTRIP_CACHE_TTL
                )
        if content:
            return Filmstrip(file_id=file_id, content=content, info=info)

    if await Redis.get("filmstrip-failed", cache_key):
        raise NotFoundException("Filmstrip is not available for this file")

    try:
        return await RequestCoalescer()(
            _generate_file_filmstrip,
            project_name,
            file_id,
            mime,
            media_info,
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.warning(f"Unable to create filmstrip of {project_name}/{file_id}: {e}")
        await Redis.set("filmstrip-failed", cache_key, "1", ttl=FAILURE_CACHE_TTL)
        raise NotFoundException("Filmstrip is not available for this file") from e


#
# Entity filmstrips
#


async def get_entity_filmstrip(
    project_name: str,
    entity_type: str,
    entity_id: str,
    *,
    user: UserEntity,
) -> Filmstrip:
    """Return the filmstrip of the latest reviewable of an entity.

    Uses the same reviewable the entity thumbnail falls back to.
    """

    if entity_type == "folder":
        resolver = resolve_folder_thumbnail_info
    elif entity_type == "task":
        resolver = resolve_task_thumbnail_info
    elif entity_type == "version":
        resolver = resolve_version_thumbnail_info
    else:
        raise ValueError(f"Unsupported entity type '{entity_type}' for filmstrip")

    thumbnail_info = await RequestCoalescer()(resolver, project_name, entity_id)
    await ensure_accessible(thumbnail_info, user)

    if not (file_id := thumbnail_info.get("file_id")):
        raise NotFoundException("Entity has no reviewable")

    return await get_file_filmstrip(project_name, file_id)


def get_filmstrip_response(filmstrip: Filmstrip, *, cache_control: str) -> Response:
    return Response(
        content=filmstrip.content,
        media_type=filmstrip.info["mime"],
        headers={
            "Cache-Control": cache_control,
            "X-File-Id": filmstrip.file_id,
            "X-Filmstrip-Frames": str(filmstrip.info["frames"]),
            "X-Filmstrip-Columns": str(filmstrip.info["columns"]),
            "X-Filmstrip-Frame-Width": str(filmstrip.info["frameWidth"]),
            "X-Filmstrip-Frame-Height": str(filmstrip.info["frameHeight"]),
        },
    )


#
# Eager generation
#

_background_tasks: set[asyncio.Task[None]] = set()


def schedule_filmstrip_creation(project_name: str, file_id: str) -> None:
    """Create a filmstrip of a file in the background"""

    async def create() -> None:
        try:
            await get_file_filmstrip(project_name, file_id)
        except NotFoundException:
            pass
        except Exception:
            log_traceback(f"Unable to create filmstrip of {project_name}/{file_id}")

    task = asyncio.create_task(create())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
