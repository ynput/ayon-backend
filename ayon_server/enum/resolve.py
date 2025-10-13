import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import BadRequestException

from .enum_item import EnumItem
from .resolvers import RESOLVERS


async def resolve_enum(
    enum_name: str,
    user: UserEntity | None = None,
    context: dict[str, Any] | None = None,
) -> list[EnumItem]:
    resolver: Callable[..., list[EnumItem] | Awaitable[list[EnumItem]]]

    try:
        resolver = RESOLVERS[enum_name]
    except KeyError:
        raise BadRequestException(f"Unknown enum resolver '{enum_name}'")

    context = context or {}
    if user is not None:
        context["user"] = user

    resolver_args = inspect.getfullargspec(resolver).args
    ctx_data = {}
    for key in resolver_args:
        if key in context:
            ctx_data[key] = context[key]
        else:
            ctx_data[key] = None

    enum: list[EnumItem]

    if inspect.iscoroutinefunction(resolver):
        enum = await resolver(**ctx_data)
    else:
        enum = resolver(**ctx_data)  # type: ignore
    return enum
