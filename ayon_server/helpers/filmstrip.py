"""Filmstrips - hover-scrub previews of video files.

A filmstrip is a single AVIF image containing `frames` frames of a video,
laid out in a grid of `columns` columns, left to right, top to bottom.
Regardless of the video length, frame `i` is taken from the middle of
the i-th of `frames` equally long segments of the video, so clients can map
a relative cursor position over a thumbnail directly to a frame:
`index = floor(x / width * frames)`.

Filmstrips are generated lazily (on the first request) or eagerly when
a video reviewable is uploaded, only by one server instance at a time.
They are stored in the project storage under the ID of the source file
and described in the `filmstrip` key of the file record data, which is also
part of the (cached) thumbnail info of entities using the reviewable.

The API returns the filmstrip description with an URL of the image
(a signed URL for S3 storages), so serving a filmstrip never needs
to access the storage and the image bytes are not cached by the server.
"""

import asyncio
import io
import math
import os
import time
from typing import Any, TypedDict, TypeGuard

import aiofiles
import aiofiles.tempfile
from fastapi import Response
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image
from starlette.concurrency import run_in_threadpool

from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    AyonException,
    NotFoundException,
    ServiceUnavailableException,
)
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
from ayon_server.types import Field, OPModel
from ayon_server.utils.request_coalescer import RequestCoalescer

# Max number of filmstrips generated at the same time by this server instance
FILMSTRIP_SEMAPHORE = asyncio.Semaphore(2)

# Only one server instance creates a filmstrip of a file, others wait for it.
# The lock outlives the worst case generation (single pass + seeking fallback)
LOCK_TTL = 300
LOCK_WAIT_TIMEOUT = 60
LOCK_POLL_INTERVAL = 0.5

# Videos up to this many frames are decoded in a single pass, which is much
# faster than seeking for short, long-GOP clips. Longer videos are sampled
# by seeking to each frame in parallel processes.
SINGLE_PASS_MAX_FRAMES = 1500

# Max number of ffmpeg processes extracting frames for a single filmstrip
FRAME_CONCURRENCY = 4

# Max time to extract frames (seconds)
FRAME_TIMEOUT = 30
SINGLE_PASS_TIMEOUT = 120

FAILURE_CACHE_TTL = 3600

# Validity of signed S3 URLs. Must be longer than the API response cache time.
FILMSTRIP_URL_TTL = 3600

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
    """Create a filmstrip image from a video file (path or URL).

    Callers limit the concurrency with FILMSTRIP_SEMAPHORE.
    """

    if duration <= 0:
        raise AyonException("Cannot create a filmstrip of a video without duration")

    kwargs: dict[str, Any] = {
        "duration": duration,
        "frames": frames,
        "frame_size": frame_size,
        "stream_index": stream_index,
    }

    results: list[bytes | None] = []
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


class FilmstripModel(OPModel):
    file_id: str = Field(..., title="ID of the video file of the filmstrip")
    url: str = Field(..., title="URL of the filmstrip image")
    frames: int = Field(..., title="Number of frames")
    columns: int = Field(..., title="Number of grid columns")
    frame_width: int = Field(..., title="Width of a frame in pixels")
    frame_height: int = Field(..., title="Height of a frame in pixels")


def _is_current(info: Any) -> TypeGuard[FilmstripInfo]:
    """Check whether stored filmstrip info matches the current configuration"""
    if not info:
        return False
    return (
        info.get("version") == FILMSTRIP_VERSION
        and info.get("frames") == ayonconfig.filmstrip_frames
        and info.get("frameSize") == ayonconfig.filmstrip_frame_size
    )


async def _get_filmstrip_model(
    project_name: str,
    file_id: str,
    info: FilmstripInfo,
) -> FilmstripModel:
    storage = await Storages.project(project_name)
    if storage.storage_type == "s3":
        # Signing is done locally, it does not access S3
        url = await storage.get_signed_url(
            file_id,
            file_group="filmstrips",
            ttl=FILMSTRIP_URL_TTL,
            content_type=info["mime"],
        )
    else:
        # Changes when the filmstrip is re-created with other settings,
        # so browsers may cache the payload
        version = f"{info['version']}.{info['frames']}.{info['frameSize']}"
        url = f"/api/projects/{project_name}/files/{file_id}/filmstrip/payload"
        url += f"?v={version}"

    return FilmstripModel(
        file_id=file_id,
        url=url,
        frames=info["frames"],
        columns=info["columns"],
        frame_width=info["frameWidth"],
        frame_height=info["frameHeight"],
    )


async def _get_file_data(project_name: str, file_id: str) -> dict[str, Any]:
    row = await Postgres.fetchrow(
        f"SELECT data FROM project_{project_name}.files WHERE id = $1",
        file_id,
    )
    if not row:
        raise NotFoundException("File not found")
    return row["data"] or {}


async def _invalidate_thumbnail_info(project_name: str, file_id: str) -> None:
    """Drop the cached thumbnail info of entities using the reviewable,
    so it includes the new filmstrip"""

    res = await Postgres.fetchrow(
        f"""
        SELECT v.id AS version_id, v.task_id, p.folder_id
        FROM project_{project_name}.files f
        JOIN project_{project_name}.activity_feed a
            ON a.activity_id = f.activity_id
            AND a.entity_type = 'version'
            AND a.activity_type = 'reviewable'
            AND a.reference_type = 'origin'
        JOIN project_{project_name}.versions v
            ON v.id = a.entity_id
        JOIN project_{project_name}.products p
            ON p.id = v.product_id
        WHERE f.id = $1
        """,
        file_id,
    )
    if not res:
        return
    for entity_id in (res["version_id"], res["task_id"], res["folder_id"]):
        if entity_id:
            await Redis.delete("thumbnail-info", f"{project_name}:{entity_id}")


async def _generate_file_filmstrip(
    project_name: str,
    file_id: str,
    media_info: dict[str, Any],
) -> FilmstripInfo:
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
    await _invalidate_thumbnail_info(project_name, file_id)
    return info


async def _create_file_filmstrip(
    project_name: str,
    file_id: str,
    media_info: dict[str, Any],
) -> FilmstripInfo:
    """Create a filmstrip, or wait for another server instance creating it"""

    lock_key = f"{project_name}:{file_id}"
    deadline = time.monotonic() + LOCK_WAIT_TIMEOUT
    while True:
        async with FILMSTRIP_SEMAPHORE:
            token = await Redis.acquire_lock("filmstrip-lock", lock_key, LOCK_TTL)
            if token:
                try:
                    # It may have been created while waiting for the lock
                    info = (await _get_file_data(project_name, file_id)).get(
                        "filmstrip"
                    )
                    if _is_current(info):
                        return info
                    return await _generate_file_filmstrip(
                        project_name, file_id, media_info
                    )
                finally:
                    await Redis.release_lock("filmstrip-lock", lock_key, token)

        await asyncio.sleep(LOCK_POLL_INTERVAL)
        info = (await _get_file_data(project_name, file_id)).get("filmstrip")
        if _is_current(info):
            return info
        if await Redis.get("filmstrip-failed", lock_key):
            raise NotFoundException("Filmstrip is not available for this file")
        if time.monotonic() > deadline:
            raise ServiceUnavailableException("Filmstrip is being created")


async def _ensure_file_filmstrip(
    project_name: str,
    file_id: str,
    data: dict[str, Any],
) -> FilmstripInfo:
    """Return the filmstrip info of a file, creating the filmstrip if needed.

    Raises NotFoundException if a filmstrip cannot be created for the file
    (not a video, broken file...)
    """

    mime = data.get("mime", "application/octet-stream")
    media_info = data.get("mediaInfo") or {}
    info = data.get("filmstrip")

    if not is_video_mime_type(mime):
        raise NotFoundException(f"Filmstrips are not available for {mime} files")

    if media_info and media_info.get("videoTrackIndex") is None:
        raise NotFoundException("File has no video track")

    if _is_current(info):
        return info

    failure_key = f"{project_name}:{file_id}"
    if await Redis.get("filmstrip-failed", failure_key):
        raise NotFoundException("Filmstrip is not available for this file")

    try:
        return await RequestCoalescer()(
            _create_file_filmstrip,
            project_name,
            file_id,
            media_info,
        )
    except (NotFoundException, ServiceUnavailableException):
        raise
    except Exception as e:
        logger.warning(f"Unable to create filmstrip of {project_name}/{file_id}: {e}")
        await Redis.set("filmstrip-failed", failure_key, "1", ttl=FAILURE_CACHE_TTL)
        raise NotFoundException("Filmstrip is not available for this file") from e


async def get_file_filmstrip(project_name: str, file_id: str) -> FilmstripModel:
    """Return the filmstrip of a video file, creating it if needed."""

    file_id = file_id.replace("-", "")
    data = await _get_file_data(project_name, file_id)
    info = await _ensure_file_filmstrip(project_name, file_id, data)
    return await _get_filmstrip_model(project_name, file_id, info)


async def get_filmstrip_payload_response(project_name: str, file_id: str) -> Response:
    """Serve the filmstrip image (used for local storages)"""

    storage = await Storages.project(project_name)
    if storage.storage_type == "s3":
        url = await storage.get_signed_url(
            file_id,
            file_group="filmstrips",
            ttl=FILMSTRIP_URL_TTL,
            content_type=FILMSTRIP_MIME,
        )
        return RedirectResponse(url=url, status_code=302)

    path = await storage.get_path(file_id, file_group="filmstrips")
    if not os.path.isfile(path):
        raise NotFoundException("Filmstrip not found")
    # the URL changes when the filmstrip is re-created
    return FileResponse(
        path,
        media_type=FILMSTRIP_MIME,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


#
# Entity filmstrips
#


async def get_entity_filmstrip(
    project_name: str,
    entity_type: str,
    entity_id: str,
    *,
    user: UserEntity,
) -> FilmstripModel:
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

    info = thumbnail_info.get("filmstrip")
    if _is_current(info):
        # Usually served just from the cached thumbnail info
        return await _get_filmstrip_model(project_name, file_id, info)
    return await get_file_filmstrip(project_name, file_id)


#
# Eager generation
#

_background_tasks: set[asyncio.Task[None]] = set()


def schedule_filmstrip_creation(project_name: str, file_id: str) -> None:
    """Create a filmstrip of a file in the background"""

    async def create() -> None:
        try:
            data = await _get_file_data(project_name, file_id)
            await _ensure_file_filmstrip(project_name, file_id, data)
        except (NotFoundException, ServiceUnavailableException):
            pass
        except Exception:
            log_traceback(f"Unable to create filmstrip of {project_name}/{file_id}")

    task = asyncio.create_task(create())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
