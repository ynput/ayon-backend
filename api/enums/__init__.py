__all__ = ["router"]


from typing import Annotated, Any

from fastapi import APIRouter, Path, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import UserEntity
from ayon_server.enum import EnumItem, EnumRegistry, EnumResolverInfo
from ayon_server.exceptions import BadRequestException
from ayon_server.logging import logger

from .parse_enum_param import parse_enum_param

router = APIRouter(tags=["Enums"])

#
# GET
#


@router.get("/enum/{enum_name}", response_model_exclude_none=True)
async def get_enum(
    request: Request,
    enum_name: Annotated[
        str,
        Path(
            description="Name of the enum",
            regex=r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?$",
        ),
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

    context: dict[str, Any] = {"user": current_user}

    accepted_params = await EnumRegistry.get_accepted_params(enum_name)

    query_params = request.query_params
    for param_name, param_type in accepted_params.items():
        if param_name in query_params:
            try:
                raw_value = query_params[param_name]
            except KeyError:
                continue  # Parameter not provided, skip

            if isinstance(raw_value, str):
                context[param_name] = parse_enum_param(param_type, raw_value)

            logger.warning(
                f"Expected string value for parameter '{param_name}' "
                f"got {type(raw_value).__name__}"
            )

    user_name = query_params.get("user")
    if user_name is not None:
        if not current_user.is_admin:
            raise BadRequestException("Only admins can resolve enums for another user")
        context["user"] = await UserEntity.load(user_name)

    # logger.trace(f"Resolving enum '{enum_name}' with context: {context}")

    return await EnumRegistry.resolve(
        enum_name,
        **context,
    )


@router.get("/enum", response_model=list[EnumResolverInfo], tags=["Enums"])
async def list_enums(current_user: CurrentUser) -> list[EnumResolverInfo]:
    """List all available enum resolvers."""
    _ = current_user
    return await EnumRegistry.list_resolvers()
