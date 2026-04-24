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
    new_code: str | None = None,
) -> None:
    """Rename a project and update related project references.

    This updates the project's name in ``public.projects``. For non-skeleton
    projects, it also renames the corresponding ``project_<name>`` PostgreSQL
    schema and reassigns user ``accessGroups`` entries keyed by the old project
    name to the new one.

    After the transaction completes, the project list is rebuilt and a
    ``entity.<type>.renamed`` event is dispatched.

    Limitations:
        - Non-skeleton projects cannot be renamed if they contain thumbnails.
        - Non-skeleton projects cannot be renamed if they contain files.
    """
    async with Postgres.transaction():
        project = await ProjectEntity.load(old_name)
        etype = "project_skeleton" if project.skeleton else "project"

        if new_code is None:
            new_code = project.code

        try:
            await Postgres.execute(
                "UPDATE public.projects SET name = $1, code=$2 WHERE name = $3",
                new_name,
                new_code,
                old_name,
            )
        except Postgres.UniqueViolationError:
            raise BadRequestException(
                f"Project name {new_name} ({new_code}) already exists."
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
