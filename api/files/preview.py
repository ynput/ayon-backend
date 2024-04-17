from fastapi import Response

from ayon_server.lib.redis import Redis

REDIS_NS = "project.file_preview"


async def obtain_file_preview(project_name: str, file_id: str) -> bytes:
    pass


async def get_file_preview(project_name: str, file_id: str) -> Response:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32

    key = f"{project_name}.{file_id}"
    pvw_bytes = await Redis.get(REDIS_NS, key)

    if pvw_bytes is None:
        pvw_bytes = await obtain_file_preview(project_name, file_id)
        await Redis.set(REDIS_NS, key, pvw_bytes)

    return Response(content=pvw_bytes, media_type="image/jpeg")
