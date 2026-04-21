from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.project_list import build_project_list
from ayon_server.lib.postgres import Postgres


async def _reassign_access_groups(old_project_name: str, new_project_name: str) -> None:
    """Reassigns access groups from the old project to the new project."""
    query = """
        UPDATE users
        SET data = jsonb_set(
            data,
            '{accessGroups}',
            (
                (data->'accessGroups') - $1::text
            ) || jsonb_build_object(
                $2::text,
                data->'accessGroups'->$1::text
            )
        )
        WHERE data->'accessGroups' ? $1::text;
    """
    await Postgres.execute(query, old_project_name, new_project_name)


async def _sanity_check_full_project(project_name: str) -> None:
    """
    Performs a sanity check to ensure that the
    project can be renamed without issues.
    """

    res = await Postgres.fetchrow(
        f"SELECT COUNT(*) FROM project_{project_name}.thumbnails"
    )
    if res and res[0] > 0:
        raise BadRequestException(
            f"Project {project_name} has thumbnails, cannot rename."
        )

    res = await Postgres.fetchrow(f"SELECT COUNT(*) FROM project_{project_name}.files")
    if res and res[0] > 0:
        raise BadRequestException(f"Project {project_name} has files, cannot rename.")


async def rename_project(
    old_name: str,
    new_name: str,
) -> None:
    """Changes the user name of a user in the database and all references to it.

    Requires only old_name and new_name as arguments. The rest are optional and
    is used only for logging purposes.
    """
    async with Postgres.transaction():
        project = await ProjectEntity.load(old_name)
        etype = "project_skeleton" if project.skeleton else "project"

        await Postgres.execute(
            "UPDATE public.projects SET name = $1 WHERE name = $2",
            new_name,
            old_name,
        )

        if not project.skeleton:
            await _sanity_check_full_project(old_name)

            old_schema_name = f"project_{old_name}"
            new_schema_name = f"project_{new_name}"

            query = f"ALTER SCHEMA {old_schema_name} RENAME TO {new_schema_name}"
            await Postgres.execute(query)

            await _reassign_access_groups(old_name, new_name)

    await build_project_list()

    await EventStream.dispatch(
        f"entity.{etype}.renamed",
        description=f"Renamed project {old_name} to {new_name}",
        summary={"entityName": old_name},
        payload={"oldValue": old_name, "newValue": new_name},
    )
