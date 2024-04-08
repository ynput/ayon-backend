import httpx
from fastapi import Response

from ayon_server.api.dependencies import CurrentUser, UserName
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.thumbnails import process_thumbnail
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .router import router

REDIS_NS = "user.avatar"


def create_initials_svg(
    initials: str,
    width: int = 100,
    height: int = 100,
    bg_color: str = "#000000",
    text_color: str = "white",
) -> str:
    svg_template = f"""
    <svg width="{width}px" height="{height}px" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="{bg_color}"/>
      <text
        x="50%"
        y="50%"
        dominant-baseline="middle"
        text-anchor="middle"
        fill="{text_color}"
        font-size="{height // 2}px"
        font-family="Arial"
      >
        {initials}
      </text>
    </svg>
    """

    return svg_template.strip()


async def obtain_avatar(user_name: str) -> bytes:
    # skip loading the entire user object.
    # we just need one single attribute

    res = await Postgres.fetch(
        """
        SELECT
            attrib->>'avatarUrl' as url,
            attrib->>'fullName' as full_name
        FROM users WHERE name = $1
        """,
        user_name,
    )

    if not res:
        raise NotFoundException("User not found")

    if res[0]["url"]:
        avatar_url = res[0]["url"]
        async with httpx.AsyncClient() as client:
            response = await client.get(avatar_url)
            avatar_bytes = response.content
        avatar_bytes = await process_thumbnail(avatar_bytes)
    else:
        name = res[0]["full_name"] or user_name
        initials = "".join([n[0] for n in name.split()])
        initials = initials.upper()
        avatar_bytes = create_initials_svg(initials).encode()

    await Redis.set(REDIS_NS, user_name, avatar_bytes)
    return avatar_bytes


@router.get("/{user_name}/avatar")
async def get_avatar(user_name: UserName) -> Response:  # user: CurrentUser):
    avatar_bytes = await Redis.get(REDIS_NS, user_name)

    if not avatar_bytes:
        avatar_bytes = await obtain_avatar(user_name)

    if avatar_bytes[0:4] == b"\x89PNG":
        return Response(content=avatar_bytes, media_type="image/png")
    elif avatar_bytes[0:2] == b"\xff\xd8":
        return Response(content=avatar_bytes, media_type="image/jpeg")
    elif avatar_bytes[0:4] == b"<svg":
        return Response(content=avatar_bytes, media_type="image/svg+xml")

    raise NotFoundException("Invalid avatar format")


@router.put("/avatar")
async def set_avatar(user: CurrentUser):
    pass
