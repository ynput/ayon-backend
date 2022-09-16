from typing import TYPE_CHECKING, Literal

from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres
from openpype.types import AccessType, ProjectLevelEntityType
from openpype.utils import SQLTool

if TYPE_CHECKING:
    from openpype.entities import UserEntity


def path_to_paths(
    path: str,
    include_parents: bool = False,
    include_self: bool = True,
) -> list[str]:
    path = path.strip().strip("/")
    pelms = path.split("/")
    result = [f'"{path}/%"']
    if include_parents:
        for i in range(len(pelms)):
            result.append(f"\"{'/'.join(pelms[0:i+1])}\"")
    elif include_self:
        result.append("/".join(pelms))
    return result


async def folder_access_list(
    user: "UserEntity",
    project_name: str,
    access_type: AccessType = "read",
) -> list[str] | None:
    """Return a list of paths user has access to

    Result is either a list of strings or None,
    if there's no access limit, so if the result is not none,

    ```

    Requires folowing columns to be selected:
        - hierarchy.path AS path

    Raises ForbiddenException in case it is obvious the user
    does not have rights to access any of the folders in the project.
    """

    if user.is_manager:
        return None

    perms = user.permissions(project_name)
    assert perms is not None, "folder_access_list without selected project"

    permset = perms.__getattribute__(access_type)
    if not permset.enabled:
        return None

    fpaths = set()

    for perm in permset.access_list:
        if perm.access_type == "hierarchy":
            for path in path_to_paths(
                perm.path,
                # Read access implies reading parent folders
                include_parents=access_type == "read",
            ):
                fpaths.add(path)

        elif perm.access_type == "children":
            for path in path_to_paths(
                perm.path,
                include_parents=access_type == "read",
                include_self=False,
            ):
                fpaths.add(path)

        elif perm.access_type == "assigned":
            query = f"""
                SELECT
                    h.path
                FROM
                    project_{project_name}.hierarchy as h
                INNER JOIN
                    project_{project_name}.tasks as t
                    ON h.id = t.folder_id
                WHERE
                    '{user.name}' = ANY (t.assignees)
                """
            async for record in Postgres.iterate(query):
                for path in path_to_paths(
                    record["path"],
                    include_parents=access_type == "read",
                    include_self=True,
                ):
                    fpaths.add(path)

    if not fpaths:
        raise ForbiddenException("No paths")

    return list(fpaths)


async def ensure_entity_access(
    user: "UserEntity",
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
    access_type: AccessType = "read",
) -> Literal[True]:
    """Check whether the user has access to a given entity.

    Warning: THIS IS SLOW. DO NOT USE IN BATCHES!
    """

    access_list = await folder_access_list(user, project_name, access_type=access_type)
    if access_list is None:
        return True

    conditions = [f"hierarchy.path like ANY ('{{{', '.join(access_list)}}}')"]
    joins = []

    if entity_type in ["subset", "version", "representation"]:
        joins.append(
            f"""
            INNER JOIN project_{project_name}.subsets
            ON subsets.folder_id = hierarchy.id
            """
        )
        if entity_type in ["version", "representation"]:
            joins.append(
                f"""
                INNER JOIN project_{project_name}.versions
                ON versions.subset_id = subsets.id
                """
            )
            if entity_type == "representation":
                joins.append(
                    f"""
                    INNER JOIN project_{project_name}.representations
                    ON representations.version_id = versions.id
                    """
                )

    elif entity_type == "task":
        joins.append(
            f"INNER JOIN project_{project_name}.tasks ON tasks.folder_id = hierarchy.id"
        )

    if entity_type == "folder":
        conditions.append(f"hierarchy.id = '{entity_id}'")
    else:
        conditions.append(f"{entity_type}s.id = '{entity_id}'")

    query = f"""
        SELECT hierarchy.id FROM project_{project_name}.hierarchy
        {" ".join(joins)}
        {SQLTool.conditions(conditions)}
    """

    async for row in Postgres.iterate(query):
        return True
    raise ForbiddenException("Entity access denied")
