from typing import Annotated

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.helpers.entity_access import EntityAccessHelper, ShareOption
from ayon_server.types import PROJECT_NAME_REGEX, OPModel

from .router import router


class ShareOptions(OPModel):
    options: list[ShareOption]


@router.get("/share")
async def get_share_options(
    user: CurrentUser,
    project_name: Annotated[str | None, Query(regex=PROJECT_NAME_REGEX)] = None,
) -> ShareOptions:
    opts = await EntityAccessHelper.get_share_options(
        user,
        project_name=project_name,
    )
    return ShareOptions(options=opts)
