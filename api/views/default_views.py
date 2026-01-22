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
    query_parts = []
    params = [default_view_id, view_type, user_name]

    # Highest Priority: Explicit ID in Project Schema
    if project_name:
        query_parts.append(f"""
            SELECT *, 'project' AS scope, 1 AS priority
            FROM project_{project_name}.views
            WHERE id = $1
        """)

    # Second Priority: Explicit ID in Public Schema
    query_parts.append("""
        SELECT *, 'studio' AS scope, 2 AS priority
        FROM public.views
        WHERE id = $1
    """)

    # Third Priority: Working View (Project or Public)
    if project_name:
        query_parts.append(f"""
            SELECT *, 'project' AS scope, 3 AS priority
            FROM project_{project_name}.views
            WHERE view_type = $2 AND owner = $3 AND working = true
        """)

    query_parts.append("""
        SELECT *, 'studio' AS scope, 4 AS priority
        FROM public.views
        WHERE view_type = $2 AND owner = $3 AND working = true
    """)

    # Lowest Priority: Base View in Public
    query_parts.append("""
        SELECT *, 'studio' AS scope, 5 AS priority
        FROM public.views
        WHERE view_type = $2 AND label = '__base__'
    """)

    # Combine everything
    final_query = f"""
        WITH candidates AS (
            {" UNION ALL ".join(query_parts)}
        )
        SELECT * FROM candidates
        WHERE id IS NOT NULL
        ORDER BY priority ASC
        LIMIT 1
    """

    row = await Postgres.fetchrow(final_query, *params)

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
