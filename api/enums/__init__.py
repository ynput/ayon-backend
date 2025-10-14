__all__ = ["router"]


from typing import Annotated

from fastapi import APIRouter, Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.enum.enum_item import EnumItem
from ayon_server.enum.resolve import enum_resolver
from ayon_server.types import PROJECT_NAME_REGEX

router = APIRouter(tags=["Enums"])

#
# Context vars
#

QProjectName = Annotated[
    str | None,
    Query(description="Project name", regex=PROJECT_NAME_REGEX),
]


#
# GET
#


@router.get("/enum/{enum_name}")
async def get_enum(
    enum_name: Annotated[
        str,
        Path(description="Name of the enum", regex="^[a-zA-Z_][a-zA-Z0-9_]*$"),
    ],
    current_user: CurrentUser,
    project_name: QProjectName = None,
) -> list[EnumItem]:
    """Get enum values by name."""

    context = {
        "project_name": project_name,
    }

    return await enum_resolver.resolve(
        enum_name,
        user=current_user,
        context=context,
    )
