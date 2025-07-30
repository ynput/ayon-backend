from typing import Annotated, Any

from fastapi import Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EntityIdResponse
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, PROJECT_NAME_REGEX

from .development import recreate_views_tables
from .models import ViewListItemModel, ViewListModel, ViewModel, construct_view_model
from .router import router

QProjectName = Annotated[
    str | None,
    Query(title="Project name", regex=PROJECT_NAME_REGEX),
]
PViewType = Annotated[str, Path(regex=NAME_REGEX)]
PViewId = Annotated[str, Path(title="View ID", regex=r"^[0-9a-f]{32}$")]


# TODO: Remove before merging and move DB initialization to migrations
@router.post("/__init__")
async def init_views(current_user: CurrentUser) -> None:
    """Reinitialize the views table. This is for development purposes only."""

    await recreate_views_tables()


def row_to_list_item(row: dict[str, Any]) -> ViewListItemModel:
    """Convert a database row to a ViewListItemModel."""

    access = row.get("access") or {}
    if row["visibility"] == "public":
        # TODO: Handle access control for public views
        _ = access

    return ViewListItemModel(
        id=row["id"],
        scope="studio",
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        personal=row.get("personal", False),
    )


@router.get("/{view_type}")
async def list_views(
    current_user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewListModel:
    """Get the list of views available to the user."""

    # Load views from the public schema

    query = """
        SELECT
            id, label, position, owner, visibility, personal, access
        FROM views
        WHERE view_type = $1 AND (owner = $2 OR visibility = 'public')
        ORDER BY position ASC
    """

    views: list[ViewListItemModel] = []

    async with Postgres.transaction():
        res = await Postgres.fetch(query, view_type, current_user.name)
        for row in res:
            views.append(row_to_list_item(row))

        if project_name:
            await Postgres.set_project_schema(project_name)
            res = await Postgres.fetch(query, view_type, current_user.name)
            for row in res:
                views.append(row_to_list_item(row))

    return ViewListModel(views=views)


@router.get("/{view_type}/{view_id}")
async def get_view(
    current_user: CurrentUser,
    view_type: PViewType,
    view_id: PViewId,
    project_name: QProjectName = None,
) -> ViewModel:
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
            raise ValueError("View not found")

        return construct_view_model(
            id=row["id"],
            view_type=row["view_type"],
            scope="studio" if project_name is None else "project",
            label=row["label"],
            position=row.get("position", 0),
            owner=row["owner"],
            visibility=row.get("visibility", "private"),
            personal=row.get("personal", False),
            settings=row.get("data", {}),
        )


@router.post("/{view_type}")
async def create_view(
    current_user: CurrentUser,
    view_type: PViewType,
    payload: ViewModel,
    project_name: QProjectName = None,
) -> EntityIdResponse:
    """Create a new view for the user."""

    # TODO: allow owner override

    async with Postgres.transaction():
        if project_name:
            print(f"Setting project schema to: {project_name}")
            await Postgres.set_project_schema(project_name)

        query = """
            INSERT INTO views (
                id,
                view_type,
                label,
                position,
                owner,
                visibility,
                personal,
                access,
                data
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """

        await Postgres.execute(
            query,
            payload.id,
            view_type,
            payload.label,
            payload.position,
            current_user.name,
            payload.visibility,
            payload.personal,
            {},  # Access control is not implemented yet
            payload.settings.dict(),
        )

    return EntityIdResponse(id=payload.id)
