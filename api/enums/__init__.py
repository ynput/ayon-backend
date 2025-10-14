__all__ = ["router"]


from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.enum.enum_item import EnumItem
from ayon_server.enum.enum_resolver import enum_resolver
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


@router.get("/enum/{enum_name}", response_model_exclude_none=True)
async def get_enum(
    request: Request,
    enum_name: Annotated[
        str,
        Path(description="Name of the enum", regex="^[a-zA-Z_][a-zA-Z0-9_]*$"),
    ],
    current_user: CurrentUser,
) -> list[EnumItem]:
    """Get enum values by name."""

    context = {}
    accepted_params = await enum_resolver.get_accepted_params(enum_name)

    query_params = request.query_params
    for param_name, param_type in accepted_params.items():
        if param_name in query_params:
            raw_value = query_params[param_name]
            if param_type is bool:
                value = raw_value.lower() in ("1", "true", "yes", "on")
            else:
                value = param_type(raw_value)
            context[param_name] = value

    return await enum_resolver.resolve(
        enum_name,
        user=current_user,
        context=context,
    )
