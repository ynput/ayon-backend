import copy
from typing import Annotated

from fastapi import BackgroundTasks, Body, Query

from ayon_server.access.permissions import Permissions
from ayon_server.api.dependencies import (
    AccessGroupName,
    CurrentUser,
    ProjectNameOrUnderscore,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.events import EventStream
from ayon_server.exceptions import (
    ConstraintViolationException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback
from ayon_server.settings.postprocess import postprocess_settings_schema
from ayon_server.types import PROJECT_NAME_REGEX, Field, OPModel

from .router import router


async def clean_up_user_access_groups() -> None:
    """Remove deleted access groups from user records"""

    async with Postgres.transaction():
        res = await Postgres.fetch("SELECT name FROM public.access_groups")
        if not res:
            return
        existing_access_groups = [row["name"] for row in res]

        query = "SELECT name, data FROM public.users FOR UPDATE OF users"
        user_map = await Postgres.fetch(query)
        for row in user_map:
            user_name = row["name"]
            user_data = row["data"]
            save = False

            if def_access_groups := user_data.get("defaultAccessGroups", []):
                if isinstance(def_access_groups, list):  # just in case
                    for ag in def_access_groups:
                        if ag not in existing_access_groups:
                            def_access_groups.remove(ag)
                            save = True

            if isinstance(acc_groups := user_data.get("accessGroups", {}), dict):
                for project_access_groups in acc_groups.values():
                    if isinstance(project_access_groups, list):  # just in case
                        for ag in project_access_groups:
                            if ag not in existing_access_groups:
                                project_access_groups.remove(ag)
                                save = True

            if save:
                await Postgres.execute(
                    "UPDATE public.users SET data = $2 WHERE name = $1",
                    user_name,
                    user_data,
                )


@router.get("/accessGroups/_schema")
async def get_access_group_schema(
    project_name: Annotated[
        str | None, Query(alias="project_name", regex=PROJECT_NAME_REGEX)
    ] = None,
):
    context = {}
    if project_name:
        context["project_name"] = project_name

    schema = copy.deepcopy(Permissions.schema())
    await postprocess_settings_schema(schema, Permissions, context=context)
    return schema


class AccessGroupObject(OPModel):
    name: str = Field(
        ...,
        description="Name of the access group",
        example="artist",
    )
    is_project_level: bool = Field(
        ...,
        description="Whether the access group is project level",
        example=False,
    )


@router.get("/accessGroups/{project_name}")
async def get_access_groups(
    user: CurrentUser,
    project_name: ProjectNameOrUnderscore,
) -> list[AccessGroupObject]:
    """Get a list of access group for a given project"""

    if project_name == "_":
        query = """
            SELECT name, FALSE AS is_project_level
            FROM public.access_groups ORDER BY name
        """
    else:
        query = f"""
            SELECT g.name, p.data IS NOT NULL AS is_project_level
            FROM public.access_groups g
            LEFT JOIN project_{project_name}.access_groups p ON g.name = p.name
            ORDER BY g.name
        """
    result = []
    async for row in Postgres.iterate(query):
        result.append(
            AccessGroupObject(
                name=row["name"],
                is_project_level=row["is_project_level"],
            )
        )
    return result


@router.get(
    "/accessGroups/{access_group_name}/{project_name}",
    response_model_exclude_none=True,
)
async def get_access_group(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
) -> Permissions:
    """Get an access group definition"""
    # return AccessGroups.combine([access_group_name], project_name)

    if project_name == "_":
        query = """
            SELECT name, data
            FROM public.access_groups
            WHERE name = $1
        """
    else:
        query = f"""
            SELECT g.name, COALESCE(p.data, g.data) as data
            FROM public.access_groups g
            LEFT JOIN project_{project_name}.access_groups p ON g.name = p.name
            WHERE g.name = $1
        """

    res = await Postgres.fetchrow(query, access_group_name)
    if res is None:
        raise NotFoundException(f"Access group '{access_group_name}' not found")

    return Permissions.from_record(res["data"])


@router.put(
    "/accessGroups/{access_group_name}/{project_name}",
    status_code=204,
)
async def save_access_group(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
    data: Permissions = Body(..., description="Set of permissions"),
) -> EmptyResponse:
    """Create or update an access group.

    Use `_` as a project name to save a global access group.
    """

    if not user.is_manager:
        if project_name == "_":
            raise ForbiddenException(
                "Only managers can create or update global access groups"
            )
        user.check_permissions("project.access", project_name=project_name, write=True)

    scope = "public" if project_name == "_" else f"project_{project_name}"

    try:
        await Postgres.execute(
            f"""
            INSERT INTO {scope}.access_groups (name, data)
            VALUES ($1, $2)
            ON CONFLICT (name)
            DO UPDATE SET data = $2
            """,
            access_group_name,
            data.dict(),
        )
    except Exception:
        # TODO: which exception is raised?
        log_traceback()
        raise ConstraintViolationException(
            f"Unable to add access group {access_group_name}"
        ) from None

    description = f"Updated access group {access_group_name}"
    await EventStream.dispatch(
        "access_group.updated",
        summary={"name": access_group_name},
        description=description,
        project=project_name if project_name != "_" else None,
        user=user.name,
    )
    return EmptyResponse()


@router.delete("/accessGroups/{access_group_name}/{project_name}", status_code=204)
async def delete_access_group(
    user: CurrentUser,
    access_group_name: AccessGroupName,
    project_name: ProjectNameOrUnderscore,
    background_tasks: BackgroundTasks,
):
    """Delete an access group"""

    if not user.is_manager:
        if project_name == "_":
            raise ForbiddenException("Only managers can modify global access groups")
        user.check_permissions("project.access", project_name=project_name, write=True)

    schema = "public" if project_name == "_" else f"project_{project_name}"

    query = f"""
        WITH deleted AS (
            DELETE FROM {schema}.access_groups
            WHERE name = $1 RETURNING *
        )
        SELECT name FROM deleted
    """

    if not await Postgres.fetch(query, access_group_name):
        raise NotFoundException(f"Access group {access_group_name} not found")

    if schema == "public":
        background_tasks.add_task(clean_up_user_access_groups)

    description = f"Deleted access group {access_group_name}"
    await EventStream.dispatch(
        "access_group.deleted",
        summary={"name": access_group_name},
        description=description,
        project=project_name if project_name != "_" else None,
        user=user.name,
    )
    return EmptyResponse()
