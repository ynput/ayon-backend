from typing import Annotated, Any

from fastapi import Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EntityIdResponse
from ayon_server.entities.project import ProjectEntity
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import NAME_REGEX, PROJECT_NAME_REGEX, OPModel
from ayon_server.utils import create_uuid

from .models import (
    ViewListItemModel,
    ViewListModel,
    ViewModel,
    ViewPatchModel,
    ViewPostModel,
    construct_view_model,
)
from .router import router

PViewType = Annotated[
    str,
    Path(
        title="View type",
        regex=NAME_REGEX,
        example="overview",
    ),
]
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
    Query(
        title="Project name",
        example="my_project",
        regex=PROJECT_NAME_REGEX,
    ),
]


def row_to_list_item(row: dict[str, Any], editable: bool) -> ViewListItemModel:
    """Convert a database row to a ViewListItemModel."""
    return ViewListItemModel(
        id=row["id"],
        scope=row["scope"],
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        access=row.get("access", {}),
        working=row.get("working", False),
        editable=editable,
    )


def row_to_model(row: dict[str, Any], editable: bool) -> ViewModel:
    """Convert a database row to a ViewModel."""
    return construct_view_model(
        id=row["id"],
        view_type=row["view_type"],
        scope=row["scope"],
        label=row["label"],
        position=row.get("position", 0),
        owner=row["owner"],
        visibility=row.get("visibility", "private"),
        access=row.get("access", {}),
        working=row.get("working", False),
        settings=row.get("data", {}),
        editable=editable,
    )


@router.get("/{view_type}")
async def list_views(
    user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewListModel:
    """Get the list of views available to the user."""

    query = """
        SELECT id, label, position, owner, visibility, working, access, $3 AS scope
        FROM views WHERE view_type = $1 AND (owner = $2 OR visibility = 'public')
        ORDER BY position ASC, label ASC
    """

    views: list[ViewListItemModel] = []

    if project_name:
        project = await ProjectEntity.load(project_name)
    else:
        project = None

    async with Postgres.transaction():
        project_views = []
        studio_views = await Postgres.fetch(query, view_type, user.name, "studio")
        if project_name:
            await Postgres.set_project_schema(project_name)
            project_views.extend(
                await Postgres.fetch(query, view_type, user.name, "project")
            )
        res = project_views + studio_views
        for row in res:
            if row["visibility"] == "public":
                try:
                    await EntityAccessHelper.check(
                        user,
                        access=row.get("access") or {},
                        level=EntityAccessHelper.READ,
                        owner=row["owner"],
                        default_open=False,
                        project=project,
                    )
                except ForbiddenException:
                    continue

            editable = True
            if user.name != row.get("owner"):
                try:
                    await EntityAccessHelper.check(
                        user,
                        access=row.get("access") or {},
                        level=EntityAccessHelper.UPDATE,
                        owner=row["owner"],
                        default_open=False,
                        project=project,
                    )
                except ForbiddenException:
                    editable = False

            views.append(row_to_list_item(row, editable=editable))
    return ViewListModel(views=views)


@router.get("/{view_type}/working")
async def get_working_view(
    current_user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewModel:
    """Get the working view of the given type"""
    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        query = """
            SELECT *, $3 as scope FROM views
            WHERE view_type = $1 AND owner = $2 AND working
        """

        row = await Postgres.fetchrow(
            query,
            view_type,
            current_user.name,
            "project" if project_name else "studio",
        )
        if not row:
            raise NotFoundException(f"Working {view_type} view not found")
        return row_to_model(row, editable=True)


DEFAULT_VIEW_NS = "default-view"


@router.get("/{view_type}/default")
async def get_default_view(
    user: CurrentUser,
    view_type: PViewType,
    project_name: QProjectName = None,
) -> ViewModel:
    """Return the view set by the user as default for the given type.

    If no default view is set, it will return the working view of the user.
    If no working view is set, raise 404
    """

    key = f"{user.name}:{view_type}:{project_name or '_'}"
    view_id_bytes = await Redis.get(DEFAULT_VIEW_NS, key)
    if view_id_bytes is None:
        view_id = None
    else:
        view_id = view_id_bytes.decode("utf-8")

    query = """
        SELECT *, $4 AS scope FROM views
        WHERE id = $1
        OR (view_type = $2 AND owner = $3 AND working)
        ORDER BY working ASC
        LIMIT 1
    """

    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)
        row = await Postgres.fetchrow(
            query,
            view_id,
            view_type,
            user.name,
            "project" if project_name else "studio",
        )
        if not row:
            raise NotFoundException(f"Default {view_type} view not found")
        editable = True
        try:
            await EntityAccessHelper.check(
                user,
                access=row.get("access"),
                level=EntityAccessHelper.UPDATE,
                owner=row["owner"],
                default_open=False,
            )
        except ForbiddenException:
            editable = False
        return row_to_model(row, editable=editable)


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
            SELECT *, $4 AS scope FROM views
            WHERE id = $1
            AND view_type = $2
            AND (owner = $3 OR visibility = 'public')
        """

        row = await Postgres.fetchrow(
            query,
            view_id,
            view_type,
            current_user.name,
            "project" if project_name else "studio",
        )

        if not row:
            raise NotFoundException("View not found")
        editable = True
        if current_user.name != row.get("owner"):
            try:
                await EntityAccessHelper.check(
                    current_user,
                    access=row.get("access") or {},
                    level=EntityAccessHelper.UPDATE,
                    owner=row["owner"],
                    default_open=False,
                )
            except ForbiddenException:
                editable = False
        return row_to_model(row, editable=editable)


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
            SET label = $3, data = $6, updated_at = NOW()
            WHERE view_type = $2
            AND owner = $4
            AND working IS TRUE
            AND $5 IS TRUE
            RETURNING id
        )
        INSERT INTO views (id, view_type, label, owner, working, data)
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
            payload.working,
            payload.settings.dict(),
        )

    return EntityIdResponse(id=payload.id)


@router.patch("/{view_type}/{view_id}")
async def update_view(
    user: CurrentUser,
    view_type: PViewType,
    view_id: PViewId,
    payload: ViewPatchModel,
    project_name: QProjectName = None,
) -> None:
    """Update a view in the database."""

    async with Postgres.transaction():
        if project_name:
            await Postgres.set_project_schema(project_name)

        # Fetch the existing view to check permissions and current settings

        query = """
            SELECT label, owner, working, data, access
            FROM views WHERE id = $1
        """
        res = await Postgres.fetchrow(query, view_id)

        if res is None:
            raise NotFoundException("View not found")

        access = res.get("access") or {}

        await EntityAccessHelper.check(
            user,
            access=access,
            level=EntityAccessHelper.UPDATE,
            owner=res["owner"],
            default_open=False,
        )

        # Update the view with the new settings

        update_dict = payload.dict(exclude_unset=True)

        label = update_dict.get("label", res["label"])
        working = update_dict.get("working", res["working"])
        access = update_dict.get("access", res["access"]) or {}
        data = update_dict.get("settings", res["data"])
        owner = res["owner"]
        if "owner" in update_dict:
            if not user.is_admin:
                raise ForbiddenException("Only admins can change the owner of a view.")
            owner = update_dict["owner"]

        query = """
            UPDATE views
            SET label = $1, working = $2, data = $3,
            owner = $4, updated_at = NOW()
            WHERE id = $5
        """
        await Postgres.execute(query, label, working, data, owner, view_id)


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
