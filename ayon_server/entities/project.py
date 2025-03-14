"""ProjectEntity.

along with the project data, this entity also handles
folder_types of the project and the folder hierarchy.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ayon_server.entities.core import TopLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.entities.project_aux_tables import (
    FolderTypeDict,
    StatusTypeDict,
    TagTypeDict,
    TaskTypeDict,
    aux_table_update,
    link_types_update,
)
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import build_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool, dict_exclude, get_nickname


class ProjectEntity(TopLevelEntity):
    entity_type: str = "project"
    model: ModelSet = ModelSet("project", attribute_library["project"], False)
    original_attributes: dict[str, Any] = {}

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
        cls.original_attributes = project_data[0]["attrib"]
        return cls.from_record(payload=payload)

    #
    # Save
    #

    async def save(self, transaction=None) -> bool:
        """Save the project to the database."""
        try:
            if transaction:
                return await self._save(transaction)
            else:
                async with Postgres.acquire() as conn:
                    async with conn.transaction():
                        return await self._save(conn)
        finally:
            await build_project_list()

    async def _save(self, transaction) -> bool:
        assert self.folder_types, "Project must have at least one folder type"
        assert self.task_types, "Project must have at least one task type"
        assert self.statuses, "Project must have at least one status"

        project_name = self.name
        if self.exists:
            fields = dict_exclude(
                self.dict(exclude_none=True),
                [
                    "folder_types",
                    "task_types",
                    "link_types",
                    "statuses",
                    "tags",
                    "created_at",
                    "name",
                    "own_attrib",
                ],
            )

            fields["updated_at"] = datetime.now()

            await transaction.execute(
                *SQLTool.update(
                    "public.projects", f"WHERE name='{project_name}'", **fields
                )
            )

            if self.original_attributes != fields["attrib"]:
                await rebuild_inherited_attributes(self.name, fields["attrib"])

        else:
            # Create a project record
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
            transaction, project_name, "folder_types", self.folder_types
        )
        await aux_table_update(transaction, project_name, "task_types", self.task_types)
        await aux_table_update(transaction, project_name, "statuses", self.statuses)
        await aux_table_update(transaction, project_name, "tags", self.tags)
        await link_types_update(
            transaction, project_name, "link_types", self.link_types
        )

        return True

    #
    # Delete
    #

    async def delete(self, transaction=None) -> bool:
        """Delete existing project."""
        try:
            if transaction:
                return await self._delete(transaction)
            else:
                async with Postgres.acquire() as conn:
                    async with conn.transaction():
                        return await self._delete(conn)
        finally:
            await build_project_list()

    async def _delete(self, transaction) -> bool:
        if not self.name:
            raise KeyError("Unable to delete project. Not loaded")

        await transaction.execute(f"DROP SCHEMA project_{self.name} CASCADE")
        await transaction.execute(
            "DELETE FROM public.projects WHERE name = $1", self.name
        )
        return True

    #
    # Properties
    #

    @property
    def nickname(self) -> str:
        """Return the project nickname."""
        return get_nickname(str(self.created_at) + self.name, 2)

    @property
    def code(self) -> str:
        """Get the project code."""
        return self._payload.code  # type: ignore

    @code.setter
    def code(self, value: str) -> None:
        """Set the project code."""
        self._payload.code = value  # type: ignore

    @property
    def library(self) -> bool:
        """Return True if the entity is a library."""
        return self._payload.library  # type: ignore

    @library.setter
    def library(self, value: bool) -> None:
        """Set the entity type to library."""
        self._payload.library = value  # type: ignore

    @property
    def config(self) -> dict[str, Any]:
        """Return the entity configuration."""
        return self._payload.config  # type: ignore

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
        """Set the entity configuration."""
        self._payload.config = value  # type: ignore

    @property
    def folder_types(self) -> Sequence[FolderTypeDict]:
        """Return the folder types."""
        return self._payload.folder_types  # type: ignore

    @folder_types.setter
    def folder_types(self, value: list[dict[str, Any]]) -> None:
        """Set the folder types."""
        self._payload.folder_types = value  # type: ignore

    @property
    def task_types(self) -> Sequence[TaskTypeDict]:
        """Return the task types."""
        return self._payload.task_types  # type: ignore

    @task_types.setter
    def task_types(self, value: list[dict[str, Any]]) -> None:
        """Set the task types."""
        self._payload.task_types = value  # type: ignore

    @property
    def statuses(self) -> Sequence[StatusTypeDict]:
        """Return the statuses."""
        return self._payload.statuses  # type: ignore

    @statuses.setter
    def statuses(self, value: list[dict[str, Any]]) -> None:
        """Set the statuses."""
        self._payload.statuses = value  # type: ignore

    @property
    def tags(self) -> Sequence[TagTypeDict]:
        """Return the tags."""
        return self._payload.tags  # type: ignore

    @tags.setter
    def tags(self, value: list[dict[str, Any]]) -> None:
        """Set the tags."""
        self._payload.tags = value  # type: ignore

    # Link types. Black sheep of aux tables

    @property
    def link_types(self) -> Sequence[LinkTypeModel]:
        """Return the link types."""
        return self._payload.link_types  # type: ignore

    @link_types.setter
    def link_types(self, value: list[dict[str, Any]]) -> None:
        """Set the link types."""
        self._payload.link_types = value  # type: ignore
