import contextlib
import time
from typing import Literal

from attributes.attributes import AttributeModel, get_attribute_list
from fastapi import Depends, Request
from pydantic import ValidationError

from ayon_server.api import dep_current_user_optional
from ayon_server.api.metadata import VERSION
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

BOOT_TIME = time.time()


def get_uptime():
    return time.time() - BOOT_TIME


class SiteInfo(OPModel):
    id: str = Field(..., title="Site identifier")
    platform: Literal["linux", "windows", "darwin"] = Field(...)
    hostname: str = Field(..., title="Machine hostname")
    version: str = Field(..., title="Ayon version")
    users: list[str] = Field(..., title="List of users")


class InfoResponseModel(OPModel):
    motd: str | None = Field(
        ayonconfig.motd,
        title="Message of the day",
        description="Instance specific message to be displayed in the login page",
    )
    version: str = Field(
        VERSION,
        title="Ayon version",
        description="Version of the Ayon API",
    )
    uptime: float = Field(default_factory=get_uptime)
    user: UserEntity.model.main_model | None = Field(None)  # type: ignore
    attributes: list[AttributeModel] | None = Field(None)
    sites: list[SiteInfo] = Field(default_factory=list)


async def get_additional_info(user: UserEntity, request: Request):
    current_site: SiteInfo | None = None

    with contextlib.suppress(ValidationError):
        current_site = SiteInfo(
            id=request.headers.get("x-ayon-site-id"),
            platform=request.headers.get("x-ayon-platform"),
            hostname=request.headers.get("x-ayon-hostname"),
            version=request.headers.get("x-ayon-version"),
            users=[user.name],
        )

    sites = []
    async for row in Postgres.iterate("SELECT id, data FROM sites"):
        site = SiteInfo(id=row["id"], **row["data"])

        if current_site and site.id == current_site.id:
            current_site.users = list(set(current_site.users + site.users))
            continue

        if user.name not in site.users:
            continue

        sites.append(site)

    if current_site:
        mdata = current_site.dict()
        mid = mdata.pop("id")
        await Postgres.execute(
            """
            INSERT INTO sites (id, data)
            VALUES ($1, $2) ON CONFLICT (id)
            DO UPDATE SET data = EXCLUDED.data
            """,
            mid,
            mdata,
        )

        sites.insert(0, current_site)

    attr_list = await get_attribute_list(user)
    return {
        "attributes": attr_list.attributes,
        "sites": sites,
    }


@router.get(
    "/info",
    response_model=InfoResponseModel,
    response_model_exclude_none=True,
    tags=["System"],
)
async def get_site_info(
    request: Request,
    current_user: UserEntity | None = Depends(dep_current_user_optional),
):
    """Return site information.

    This is the initial endpoint that is called when the user opens the page.
    It returns information about the site, the current user and the configuration.

    If the user is not logged in, only the message of the day and the API version
    are returned.
    """
    additional_info = {}
    if current_user:
        additional_info = await get_additional_info(current_user, request)
    user_payload = current_user.payload if (current_user is not None) else None
    return InfoResponseModel(user=user_payload, **additional_info)
