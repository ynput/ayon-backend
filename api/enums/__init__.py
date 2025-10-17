__all__ = ["router"]


from typing import Annotated

from fastapi import APIRouter, Path, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.enum import EnumItem, EnumRegistry
from ayon_server.exceptions import BadRequestException

router = APIRouter(tags=["Enums"])

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
    """Get enum values by name.

    This endpoint retrieves the possible values of a specified enum.
    It accepts query parameters that can influence the resolution of the enum values,
    such as filtering based on user permissions or other contextual data.

    These query parameters can vary depending on the enum being requested,
    but when requested from a project context, `project_name` should be provided.
    """

    context = {}
    accepted_params = await EnumRegistry.get_accepted_params(enum_name)

    query_params = request.query_params
    for param_name, param_type in accepted_params.items():
        if param_name in query_params:
            try:
                raw_value = query_params[param_name]
                if param_type is bool:
                    value = raw_value.lower() in ("1", "true", "yes", "on")
                else:
                    value = param_type(raw_value)
                context[param_name] = value
            except (ValueError, TypeError):
                raise BadRequestException(
                    f"Invalid value for parameter '{param_name}': {raw_value}"
                ) from None

    return await EnumRegistry.resolve(
        enum_name,
        user=current_user,
        context=context,
    )
