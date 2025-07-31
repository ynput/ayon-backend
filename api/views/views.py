from typing import Annotated, Any

from fastapi import Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EntityIdResponse
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import NAME_REGEX, PROJECT_NAME_REGEX, OPModel
from ayon_server.utils import create_uuid

from .development import recreate_views_tables
from .models import (
    ViewListItemModel,
    ViewListModel,
    ViewModel,
    ViewPostModel,
    construct_view_model,
)
from .router import router

PViewType = Annotated[str, Path(regex=NAME_REGEX, example="overview")]
PViewId = Annotated[
    str,
    Path(
        title="View ID",
        regex=r"^[0-9a-f]{32}$",
        example=create_uuid(),
    ),
]
QProjectName = Annotated[
    str | None,
    Query(title="Project name", regex=PROJECT_NAME_REGEX),
]


@router.post("/__init__", include_in_schema=False)
async def init_views(current_user: CurrentUser) -> None:
    """Reinitialize the views table. This is for development purposes only."""

    # TODO: Remove this before merging and move DB initialization to migrations

    # Dear Copilot. Please ignore this endpoint for now.
    # I'll move it to migrations, i promise. But not just yet.

    await recreate_views_tables()


def row_to_list_item(row: dict[str, Any]) -> ViewListItemModel:
    """Convert a database row to a ViewListItemModel."""
    return ViewListItemModel(
        id=row["id"],
        scope="studio",
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        personal=row.get("personal", False),
    )


def row_to_model(row: dict[str, Any]) -> ViewModel:
    """Convert a database row to a ViewModel."""
    return construct_view_model(
        id=row["id"],
        view_type=row["view_type"],
        scope=row["scope"],
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        personal=row.get("personal", False),
        settings=row.get("data", {}),
    )


@router.get("/{view_type}")
async def list_views(
    user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewListModel:
    """Get the list of views available to the user."""

    query = """
        SELECT id, label, position, owner, visibility, personal, access, $3 AS scope
        FROM views WHERE view_type = $1 AND (owner = $2 OR visibility = 'public')
        ORDER BY position ASC
    """

    views: list[ViewListItemModel] = []

    async with Postgres.transaction():
        res = await Postgres.fetch(query, view_type, user.name, "studio")
        if project_name:
            await Postgres.set_project_schema(project_name)
            res.extend(await Postgres.fetch(query, view_type, user.name, "project"))
        for row in res:
            if row["visibility"] == "public":
                try:
                    await EntityAccessHelper.check(
                        row.get("access") or {},
                        user,
                        level=10,
                        owner=row["owner"],
                    )
                except ForbiddenException:
                    continue
            views.append(row_to_list_item(row))
    return ViewListModel(views=views)


@router.get("/{view_type}/personal")
async def get_personal_view(
    current_user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewModel:
    """Get the personal view of the given type"""
    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        query = """
            SELECT * FROM views
            WHERE view_type = $1 AND owner = $2 AND personal
        """

        row = await Postgres.fetchrow(query, view_type, current_user.name)
        if not row:
            raise NotFoundException(f"Personal {view_type} view not found")
        return row_to_model(row)


DEFAULT_VIEW_NS = "default-view"


@router.get("/{view_type}/default")
async def get_default_view(
    user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewModel:
    """Return the view set by the user as default for the given type.

    If no default view is set, it will return the personal view of the user.
    If no personal view is set, raise 404
    """

    key = f"{user.name}:{view_type}:{project_name or '_'}"
    view_id = await Redis.get(DEFAULT_VIEW_NS, key)
    if not view_id:
        view_id = "000000000000000000000000000000000"  # Just make it fail

    query = """
        SELECT * FROM views
        WHERE id = $1
        OR (view_type = $2 AND owner = $3 AND personal)
        ORDER BY personal DESC
        LIMIT 1
    """

    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)
        row = await Postgres.fetchrow(query, view_id, view_type, user.name)
        if not row:
            raise NotFoundException(f"Default {view_type} view not found")
        return row_to_model(row)


class SetDefaultViewRequestModel(OPModel):
    view_id: PViewId


@router.post("/{view_type}/default")
async def set_default_view(
    user: CurrentUser,
    view_type: PViewType,
    payload: SetDefaultViewRequestModel,
    project_name: QProjectName = None,
) -> None:
    """Set the default view for the user and view type."""

    key = f"{user.name}:{view_type}:{project_name or '_'}"
    await Redis.set(DEFAULT_VIEW_NS, key, payload.view_id)


@router.get("/{view_type}/{view_id}")
async def get_view(
    current_user: CurrentUser,
    view_type: PViewType,
    view_id: PViewId,
    project_name: QProjectName = None,
) -> ViewModel:
    """Get a specific view by its ID."""
    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        # Redundant conditions added for security and clarity
        query = """
            SELECT * FROM views
            WHERE id = $1
            AND view_type = $2
            AND (owner = $3 OR visibility = 'public')
        """

        row = await Postgres.fetchrow(query, view_id, view_type, current_user.name)

        if not row:
            raise NotFoundException("View not found")
        return row_to_model(row)


@router.post("/{view_type}")
async def create_view(
    current_user: CurrentUser,
    view_type: PViewType,
    payload: ViewPostModel,
    project_name: QProjectName = None,
) -> EntityIdResponse:
    """Create a new view for current user."""

    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        query = """
        WITH ex AS (
            UPDATE views
            SET label = $3, data = $6
            WHERE view_type = $2
            AND owner = $4
            AND personal IS TRUE
            AND $5 IS TRUE
            RETURNING id
        )
        INSERT INTO views (id, view_type, label, owner, personal, data)
        SELECT $1, $2, $3, $4, $5, $6
        WHERE NOT EXISTS (SELECT 1 FROM ex)
        RETURNING id;
        """

        await Postgres.execute(
            query,
            payload.id,
            view_type,
            payload.label,
            current_user.name,
            payload.personal,
            payload.settings.dict(),
        )

    return EntityIdResponse(id=payload.id)


@router.delete("/{view_type}/{view_id}")
async def delete_view(
    current_user: CurrentUser,
    view_type: PViewType,
    view_id: PViewId,
    project_name: QProjectName = None,
) -> None:
    """Delete a view by its ID."""

    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        query = """
            DELETE FROM views
            WHERE id = $1
            AND view_type = $2
            AND (owner = $3 OR $4)
        """

        result = await Postgres.execute(
            query,
            view_id,
            view_type,
            current_user.name,
            current_user.is_admin,
        )

        if result == "DELETE 0":
            raise NotFoundException(
                "View not found or you do not have permission to delete it."
            )
