from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .models import ViewModel, row_to_model

DEFAULT_VIEW_NS = "default-view"


async def set_user_default_view(
    user: UserEntity,
    view_type: str,
    view_id: str,
    *,
    project_name: str | None = None,
) -> None:
    """Set the default view for a user."""
    key = f"{user.name}:{view_type}:{project_name or '_'}"
    await Redis.set(DEFAULT_VIEW_NS, key, view_id)


async def _get_view_row(
    view_type: str,
    user_name: str,
    default_view_id: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    row = {}

    # First, try to get the view by the explicit ID

    query = "SELECT *, $2 AS scope FROM views WHERE id = $1"

    if project_name:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            row = await Postgres.fetchrow(
                query,
                default_view_id,
                "project",
            )

    # default id is not in project schema or no project specified
    # try to get it from the public schema

    if not row:
        async with Postgres.transaction():
            row = await Postgres.fetchrow(
                query,
                default_view_id,
                "studio",
            )

    # If no view by ID, try to get the working view for the user
    #
    if not row:
        async with Postgres.transaction():
            if project_name:
                await Postgres.set_project_schema(project_name)
            else:
                await Postgres.set_public_schema()
            row = await Postgres.fetchrow(
                """
                SELECT *, $3 AS scope FROM views
                WHERE view_type = $1 AND owner = $2 AND working
                ORDER BY working ASC
                """,
                view_type,
                user_name,
                "project" if project_name else "studio",
            )

    # If we still don't have a view, get the base view

    if not row:
        await Postgres.set_public_schema()
        row = await Postgres.fetchrow(
            """
            SELECT *, $2 AS scope FROM views
            WHERE view_type = $1 AND label = '__base__'
            LIMIT 1
            """,
            view_type,
            "studio" if not project_name else "project",
        )

    if not row:
        raise NotFoundException("Default view not found")
    return dict(row)


async def get_user_default_view(
    user: UserEntity,
    view_type: str,
    *,
    project_name: str | None = None,
) -> ViewModel:
    """Get the default view for a user based on view type and optional project name."""

    project = None

    key = f"{user.name}:{view_type}:{project_name or '_'}"
    view_id_bytes = await Redis.get(DEFAULT_VIEW_NS, key)
    if view_id_bytes is None:
        view_id = None
    else:
        view_id = view_id_bytes.decode("utf-8")
        if project_name:
            project = await ProjectEntity.load(project_name)

    view_data = await _get_view_row(
        view_type=view_type,
        user_name=user.name,
        default_view_id=view_id,
        project_name=project_name,
    )

    try:
        await EntityAccessHelper.check(
            user,
            access=view_data.get("access"),
            level=EntityAccessHelper.MANAGE,
            owner=view_data["owner"],
            default_open=False,
            project=project,
        )
        access_level = EntityAccessHelper.MANAGE
    except ForbiddenException as e:
        access_level = e.extra.get("access_level", 0)
    return row_to_model(view_data, access_level=access_level)
