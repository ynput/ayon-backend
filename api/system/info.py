import contextlib
import time
from typing import Literal
from urllib.parse import urlparse

from attributes.attributes import AttributeModel
from fastapi import Request
from nxtools import log_traceback
from pydantic import ValidationError

from ayon_server import __version__
from ayon_server.addons import AddonLibrary, SSOOption
from ayon_server.api.dependencies import CurrentUserOptional
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.entities.core.attrib import attribute_library
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
        example="Hello and welcome to Ayon!",
    )
    login_page_background: str | None = Field(
        default=ayonconfig.login_page_background,
        description="URL of the background image for the login page",
        example="https://i.insider.com/602ee9d81a89f20019a377c6?width=1136&format=jpeg",
    )
    login_page_brand: str | None = Field(
        default=ayonconfig.login_page_brand,
        title="Brand logo",
        description="URL of the brand logo for the login page",
    )
    version: str = Field(
        __version__,
        title="Ayon version",
        description="Version of the Ayon API",
    )
    uptime: float = Field(
        default_factory=get_uptime,
        title="Uptime",
        description="Time (seconds) since the server was started",
    )
    user: UserEntity.model.main_model | None = Field(None, title="User information")  # type: ignore
    attributes: list[AttributeModel] | None = Field(None, title="List of attributes")
    sites: list[SiteInfo] = Field(default_factory=list, title="List of sites")
    sso_options: list[SSOOption] = Field(default_factory=list, title="SSO options")


async def get_sso_options(request: Request) -> list[SSOOption]:
    referer = request.headers.get("referer")
    if referer:
        parsed_url = urlparse(referer)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    else:
        base_url = "http://localhost:5000"

    result = []
    library = AddonLibrary.getinstance()
    active_versions = await library.get_active_versions()

    for _name, definition in library.data.items():
        vers = active_versions.get(definition.name, {})
        production_version = vers.get("production", None)
        if not production_version:
            continue

        try:
            addon = definition[production_version]
        except KeyError:
            continue

        options = await addon.get_sso_options(base_url)
        if not options:
            continue

        result.extend(options)

    return result


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

    attr_list: list[AttributeModel] = []
    for row in attribute_library.info_data:
        try:
            attr_list.append(AttributeModel(**row))
        except ValidationError:
            log_traceback(f"Invalid attribute data: {row}")
            continue
    return {
        "attributes": attr_list,
        "sites": sites,
    }


@router.get("/info", response_model_exclude_none=True, tags=["System"])
async def get_site_info(
    request: Request,
    current_user: CurrentUserOptional,
) -> InfoResponseModel:
    """Return site information.

    This is the initial endpoint that is called when the user opens the page.
    It returns information about the site, the current user and the configuration.

    If the user is not logged in, only the message of the day and the API version
    are returned.
    """
    additional_info = {}
    if current_user:
        additional_info = await get_additional_info(current_user, request)
    else:
        sso_options = await get_sso_options(request)
        additional_info = {"sso_options": sso_options}
    user_payload = current_user.payload if (current_user is not None) else None
    return InfoResponseModel(user=user_payload, **additional_info)
