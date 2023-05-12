"""ProjectEntity.

along with the project data, this entity also handles
folder_types of the project and the folder hierarchy.
"""

from typing import Any, Dict

from ayon_server.entities.core import TopLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.exceptions import ConstraintViolationException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool, dict_exclude


async def aux_table_update(conn, table: str, update_data: list[dict[str, Any]]):
    """Update auxiliary table."""

    # Fetch the current data first
    old_data = {}
    for row in await conn.fetch(f"SELECT name, data FROM {table} ORDER BY position"):
        old_data[row["name"]] = row["data"]

    position = 0
    for data in update_data:
        position += 1
        name = data["name"]

        # Rename
        original_name = data.get("original_name")
        if "original_name" in data:
            del data["original_name"]
        if original_name and name != original_name:
            await conn.execute(
                f"""
                UPDATE {table} SET name = $1, position = $2, data = $3
                WHERE name = $4
                """,
                name,
                position,
                data,
                original_name,
            )

            if original_name in old_data:
                del old_data[original_name]
            continue

        # Upsert
        await conn.execute(
            f"INSERT INTO {table} (name, position, data) VALUES ($1, $2, $3) "
            f"ON CONFLICT (name) DO UPDATE SET position = $2, data = $3",
            name,
            position,
            data,
        )

        if name in old_data:
            del old_data[name]

    # Delete the rest
    if old_data:
        old_keys = list(old_data.keys())
        query = f"DELETE FROM {table} WHERE name = ANY($1)"
        await conn.execute(query, old_keys)


async def link_types_update(conn, table: str, update_data: list[LinkTypeModel]):
    existing_names: list[str] = []
    for row in await conn.fetch(f"SELECT name FROM {table}"):
        existing_names.append(row["name"])

    new_names: list[str] = []
    for link_type_data in update_data:
        name = "|".join(
            [
                link_type_data.link_type,
                link_type_data.input_type,
                link_type_data.output_type,
            ]
        )
        new_names.append(name)

        # Upsert
        await conn.execute(
            f"""
            INSERT INTO {table} (name, link_type, input_type, output_type, data)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO UPDATE SET
            link_type = $2, input_type = $3, output_type = $4, data = $5
            """,
            name,
            link_type_data.link_type,
            link_type_data.input_type,
            link_type_data.output_type,
            link_type_data.data,
        )

    for name in existing_names:
        if name not in new_names:
            await conn.execute(f"DELETE FROM {table} WHERE name = $1", name)


class ProjectEntity(TopLevelEntity):
    entity_type: str = "project"
    model: ModelSet = ModelSet("project", attribute_library["project"], False)

    #
    # Load
    #

    @classmethod
    async def load(
        cls,
        name: str,
        transaction=None,
        for_update=False,
    ) -> "ProjectEntity":
        """Load a project from the database."""

        project_name = name

        if not (
            project_data := await Postgres.fetch(
                f"""
            SELECT  *
            FROM public.projects
            WHERE name ILIKE $1
            {'FOR UPDATE' if transaction and for_update else ''}
            """,
                name,
            )
        ):
            raise NotFoundException

        # Load folder types
        folder_types = []
        for name, data in await Postgres.fetch(
            f"""
            SELECT name, data
            FROM project_{project_name}.folder_types
            ORDER BY position
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            folder_types.append({"name": name, **data})

        # Load task types
        task_types = []
        for name, data in await Postgres.fetch(
            f"""
            SELECT name, data
            FROM project_{project_name}.task_types
            ORDER BY position
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            task_types.append({"name": name, **data})

        # Load link types
        link_types = []
        for row in await Postgres.fetch(
            f"""
            SELECT name, link_type, input_type, output_type, data
            FROM project_{project_name}.link_types
            """
        ):
            link_types.append(dict(row))

        # Load statuses
        statuses = []
        for name, data in await Postgres.fetch(
            f"""
            SELECT name, data
            FROM project_{project_name}.statuses
            ORDER BY position
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            statuses.append({"name": name, **data})

        # Load tags
        tags = []
        for name, data in await Postgres.fetch(
            f"""
            SELECT name, data
            FROM project_{project_name}.tags
            ORDER BY position
            {'FOR UPDATE' if transaction and for_update else ''}
            """
        ):
            tags.append({"name": name, **data})

        payload = dict(project_data[0]) | {
            "folder_types": folder_types,
            "task_types": task_types,
            "link_types": link_types,
            "statuses": statuses,
            "tags": tags,
        }
        return cls.from_record(payload=payload)

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
                    return await self._save(conn)

    async def _save(self, transaction) -> bool:
        assert self.folder_types, "Project must have at least one folder type"
        assert self.task_types, "Project must have at least one task type"
        assert self.statuses, "Project must have at least one status"

        project_name = self.name
        if self.exists:
            try:
                await transaction.execute(
                    *SQLTool.update(
                        "public.projects",
                        f"WHERE name='{project_name}'",
                        **dict_exclude(
                            self.dict(exclude_none=True),
                            [
                                "folder_types",
                                "task_types",
                                "link_types",
                                "statuses",
                                "tags",
                                "ctime",
                                "name",
                                "own_attrib",
                            ],
                        ),
                    )
                )

            except Postgres.ForeignKeyViolationError as e:
                raise ConstraintViolationException(e.detail)

        else:
            # Create a project record
            try:
                await transaction.execute(
                    *SQLTool.insert(
                        "projects",
                        **dict_exclude(
                            self.dict(exclude_none=True),
                            [
                                "folder_types",
                                "task_types",
                                "link_types",
                                "statuses",
                                "tags",
                                "own_attrib",
                            ],
                        ),
                    )
                )
            except Postgres.UniqueViolationError:
                raise ConstraintViolationException(f"{self.name} already exists")
            # Create a new schema for the project tablespace
            await transaction.execute(f"CREATE SCHEMA project_{project_name}")

            # Create tables in the newly created schema
            await transaction.execute(
                f"SET LOCAL search_path TO project_{project_name}"
            )

            # TODO: Preload this to avoid blocking
            await transaction.execute(open("schemas/schema.project.sql").read())

        #
        # Save aux tables
        #
        await aux_table_update(
            transaction,
            f"project_{project_name}.folder_types",
            self.folder_types,
        )
        await aux_table_update(
            transaction,
            f"project_{project_name}.task_types",
            self.task_types,
        )
        await aux_table_update(
            transaction,
            f"project_{project_name}.statuses",
            self.statuses,
        )
        await aux_table_update(
            transaction,
            f"project_{project_name}.tags",
            self.tags,
        )

        await link_types_update(
            transaction,
            f"project_{project_name}.link_types",
            self.link_types,
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
                    return await self._delete(conn)

    async def _delete(self, transaction) -> bool:
        if not self.name:
            raise KeyError("Unable to delete project. Not loaded")

        await transaction.execute(f"DROP SCHEMA project_{self.name} CASCADE")
        await transaction.execute(
            "DELETE FROM public.projects WHERE name = $1", self.name
        )
        # TODO: Return false if project was not found
        return True

    #
    # Properties
    #

    @property
    def code(self) -> str:
        """Get the project code."""
        return self._payload.code

    @code.setter
    def code(self, value: str) -> None:
        """Set the project code."""
        self._payload.code = value

    @property
    def library(self) -> bool:
        """Return True if the entity is a library."""
        return self._payload.library

    @library.setter
    def library(self, value: bool):
        """Set the entity type to library."""
        self._payload.library = value

    @property
    def config(self) -> Dict[str, Any]:
        """Return the entity configuration."""
        return self._payload.config

    @config.setter
    def config(self, value: Dict[str, Any]):
        """Set the entity configuration."""
        self._payload.config = value

    @property
    def folder_types(self) -> list[dict[str, Any]]:
        """Return the folder types."""
        return self._payload.folder_types

    @folder_types.setter
    def folder_types(self, value: list[dict[str, Any]]):
        """Set the folder types."""
        self._payload.folder_types = value

    @property
    def task_types(self) -> list[dict[str, Any]]:
        """Return the task types."""
        return self._payload.task_types

    @task_types.setter
    def task_types(self, value: list[dict[str, Any]]):
        """Set the task types."""
        self._payload.task_types = value

    @property
    def link_types(self) -> list[LinkTypeModel]:
        """Return the link types."""
        return self._payload.link_types

    @link_types.setter
    def link_types(self, value: list[dict[str, Any]]):
        """Set the link types."""
        self._payload.link_types = value

    @property
    def statuses(self) -> list[dict[str, Any]]:
        """Return the statuses."""
        return self._payload.statuses

    @statuses.setter
    def statuses(self, value: list[dict[str, Any]]):
        """Set the statuses."""
        self._payload.statuses = value

    @property
    def tags(self) -> list[dict[str, Any]]:
        """Return the tags."""
        return self._payload.tags

    @tags.setter
    def tags(self, value: list[dict[str, Any]]):
        """Set the tags."""
        self._payload.tags = value
