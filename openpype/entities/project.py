"""ProjectEntity.

along with the project data, this entity also handles
folder_types of the project and the folder hierarchy.
"""

from nxtools import log_traceback, logging

from openpype.exceptions import ConstraintViolationException, RecordNotFoundException
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, dict_exclude

from .common import Entity, EntityType, attribute_library
from .models import ModelSet


async def aux_table_update(conn, table, update_data):
    """Update auxiliary table.

    Partial update of data column is not supported.
    Always provide all fields!

    When data is set to None, the row is deleted.
    When non-standard "name" key is set, the row is renamed,
    and the "name" key is removed from the update data.

    Args:
        conn (psycopg2.extensions.connection): Connection object.
        table (str): Table name.
        update_data (dict): Data to update.
    """

    # Fetch the current data first
    old_data = {}
    for row in await conn.fetch(f"SELECT name, data FROM {table}"):
        old_data[row["name"]] = row["data"]

    for name, data in update_data.items():
        if name in old_data:
            if data is None:
                # Delete
                await conn.execute(f"DELETE FROM {table} WHERE name = $1", name)

            elif "name" in data:
                # Rename
                new_name = data["name"]
                del data["name"]
                await conn.execute(
                    f"UPDATE {table} SET name = $1, data = $2 WHERE name = $3",
                    new_name,
                    data,
                    name,
                )

            else:
                # Update
                await conn.execute(
                    f"UPDATE {table} SET data = $1 WHERE name = $2",
                    data,
                    name,
                )
        else:
            # Insert
            await conn.execute(
                f"INSERT INTO {table} (name, data) VALUES ($1, $2)",
                name,
                data,
            )

        # We always get all records in the update_data (since the original)
        # model is used, so we can just delete the ones that are not in the
        # update_data.
        for name in old_data:
            if name not in update_data:
                # Delete
                await conn.execute(f"DELETE FROM {table} WHERE name = $1", name)


class ProjectEntity(Entity):
    entity_type: EntityType = EntityType.PROJECT
    entity_name: str = "project"
    model: ModelSet = ModelSet("project", attribute_library["project"], False)

    #
    # Load
    #

    @classmethod
    async def load(
        cls, project_name: str, transaction=None, for_update=False
    ) -> "ProjectEntity":
        """Load a project from the database."""

        # TODO: maybe allow different conditions?
        # TODO: Then this code may be used in graphql as well.

        if not (
            project_data := await Postgres.fetch(
                f"""
            SELECT  *
            FROM public.projects
            WHERE name = $1
            {'FOR UPDATE' if transaction and for_update else ''}
            """,
                project_name,
            )
        ):
            raise RecordNotFoundException()

        # Load folder types
        folder_types = {}
        for name, data in await Postgres.fetch(
            f"""
            SELECT name, data
            FROM project_{project_name}.folder_types
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            folder_types[name] = data

        # Load task types
        task_types = {}
        for name, data in await Postgres.fetch(
            f"""
            SELECT  name, data
            FROM project_{project_name}.task_types
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            task_types[name] = data

        try:
            return cls.from_record(
                project_name=project_name,
                exists=True,
                validate=False,
                **dict(project_data[0])
                | {"folder_types": folder_types, "task_types": task_types},
            )
        except Exception:
            log_traceback()

    #
    # Save
    #

    async def save(self, transaction=None) -> bool:
        """Save the project to the database."""
        if transaction:
            return await self._save(transaction)
        else:
            async with Postgres.acquire() as conn:
                async with conn.transaction():
                    return await (self._save(conn))

    async def _save(self, transaction) -> bool:
        if self.exists:
            logging.debug(f"Updating project {self.name}")
            # Update a project
            try:
                await transaction.execute(
                    *SQLTool.update(
                        "public.projects",
                        f"WHERE name='{self.name}'",
                        **dict_exclude(
                            self.dict(exclude_none=True),
                            ["folder_types", "task_types", "ctime", "name"],
                        ),
                    )
                )

                await aux_table_update(
                    transaction, f"project_{self.name}.folder_types", self.folder_types
                )
                await aux_table_update(
                    transaction, f"project_{self.name}.task_types", self.task_types
                )
            except Postgres.ForeignKeyViolationError as e:
                raise ConstraintViolationException(e.detail)
            return True

        # Create a project record
        await transaction.execute(
            *SQLTool.insert(
                "projects",
                **dict_exclude(
                    self.dict(exclude_none=True), ["folder_types", "task_types"]
                ),
            )
        )
        # Create a new schema for the project tablespace
        await transaction.execute(f"CREATE SCHEMA project_{self.name}")

        # Create tables in the newly created schema
        await transaction.execute(f"SET LOCAL search_path TO project_{self.name}")

        # TODO: Preload this to avoid blocking
        await transaction.execute(open("schemas/schema.project.sql").read())

        for name, data in self.folder_types.items():
            await transaction.execute(
                f"""
                INSERT INTO project_{self.name}.folder_types
                VALUES($1, $2)
                """,
                name,
                data,
            )

        for name, data in self.task_types.items():
            await transaction.execute(
                f"""
                INSERT INTO project_{self.name}.task_types
                VALUES($1, $2)
                """,
                name,
                data,
            )
        return True

    #
    # Delete
    #

    async def delete(self, transaction=None) -> bool:
        """Delete existing project."""
        if transaction:
            return await self._delete(transaction)
        else:
            async with Postgres.acquire() as conn:
                async with conn.transaction():
                    return await (self._delete(conn))

    async def _delete(self, transaction) -> bool:
        if not self.name:
            raise KeyError("Unable to delete project. Not loaded")

        await transaction.execute(f"DROP SCHEMA project_{self.name} CASCADE")
        await transaction.execute(
            "DELETE FROM public.projects WHERE name = $1", self.name
        )
        # TODO: Return false if project was not found
        return True
