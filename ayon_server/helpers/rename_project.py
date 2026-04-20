from ayon_server.entities import ProjectEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres


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
            # TODO: Additional logic for renaming non-skeleton projects

            # old_schema_name = f"project_{old_name}"
            # new_schema_name = f"project_{new_name}"
            #
            # query = f"ALTER SCHEMA {old_schema_name} RENAME TO {new_schema_name}"
            # await Postgres.execute(query)

            raise BadRequestException("Only skeleton projects can be renamed")

    await EventStream.dispatch(
        f"entity.{etype}.renamed",
        description=f"Renamed project {old_name} to {new_name}",
        summary={"entityName": old_name},
        payload={"oldValue": old_name, "newValue": new_name},
    )
