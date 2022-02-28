from typing import Literal

from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres


def path_to_paths(path: str) -> list[str]:
    path = path.strip()
    pelms = path.split("/")
    result = [f'"{path}/%"']
    for i in range(len(pelms)):
        result.append(f"\"{'/'.join(pelms[0:i+1])}\"")
    return result


async def folder_access_list(
    user: UserEntity, project_name: str, access_type: Literal["read", "write"] = "read"
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

    if perms.read == "all":
        return None

    fpaths = set()

    for perm in perms.__getattribute__(access_type):
        if perm.access_type == "hierarchy":
            for path in path_to_paths(perm.path):
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
                for path in path_to_paths(record["path"]):
                    fpaths.add(path)

    if not fpaths:
        raise ForbiddenException

    return list(fpaths)
