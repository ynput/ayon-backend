import httpx
from fastapi import Response

from ayon_server.api.dependencies import CurrentUser, UserName
from ayon_server.helpers.process_thumbnail import process_thumbnail
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .router import router

REDIS_NS = "user.avatar"


async def obtain_avatar(user_name: str) -> bytes:
    # skip loading the entire user object.
    # we just need one single attribute

    res = await Postgres.fetch(
        "SELECT attrib->>'avatarUrl' as url FROM users WHERE name = $1",
        user_name,
    )

    if res and res[0]["url"]:
        print("Loading avatar from remote", res[0]["url"])
        avatar_url = res[0]["url"]
        async with httpx.AsyncClient() as client:
            response = await client.get(avatar_url)
            avatar_bytes = response.content
    else:
        avatar_bytes = b""

    avatar_bytes = await process_thumbnail(avatar_bytes)

    await Redis.set(REDIS_NS, user_name, avatar_bytes)
    return avatar_bytes


@router.get("/{user_name}/avatar")
async def get_avatar(user_name: UserName) -> Response:  # user: CurrentUser):
    avatar_bytes = await Redis.get(REDIS_NS, user_name)
    if not avatar_bytes:
        avatar_bytes = await obtain_avatar(user_name)

    return Response(content=avatar_bytes, media_type="image/jpeg")


@router.put("/avatar")
async def set_avatar(user: CurrentUser):
    pass
