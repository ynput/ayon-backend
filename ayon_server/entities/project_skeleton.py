from datetime import datetime
from typing import Any

import aiofiles

from ayon_server.entities.project_aux_tables import (
    aux_table_update,
    link_types_update,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import SQLTool, dict_exclude

from .project import ProjectEntity


class ProjectSkeletonEntity(ProjectEntity):
    @classmethod
    async def load(
        cls,
        name: str,
        transaction: Any = None,
        for_update: bool = False,
    ) -> "ProjectSkeletonEntity":
        """Load a project skeleton entity from the database."""
        raise NotImplementedError("Use projectentity.load instead")

    def _repopulate_anatomy(self) -> None:
        from ayon_server.helpers.extract_anatomy import extract_project_anatomy

        anatomy = extract_project_anatomy(self)
        self.data["skeletonAnatomy"] = anatomy.dict()
        self.data["isSkeleton"] = True

    async def save(self, *args, **kwargs) -> bool:
        assert self.folder_types, "Project must have at least one folder type"
        assert self.task_types, "Project must have at least one task type"
        assert self.statuses, "Project must have at least one status"

        self.config.pop("productTypes", None)  # legacy

        if "promote" not in kwargs:
            self._repopulate_anatomy()

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
                    "skeleton",
                ],
            )

            fields["updated_at"] = datetime.now()

            await Postgres.execute(
                *SQLTool.update(
                    "public.projects", f"WHERE name='{project_name}'", **fields
                )
            )

        else:
            # Create a project record
            await Postgres.execute(
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
                            "skeleton",
                        ],
                    ),
                )
            )
        await self.commit()
        return True

    async def delete(self, *args, **kwargs) -> bool:
        """Delete existing project."""
        if not self.name:
            raise KeyError("Unable to delete project. Not loaded")

        async with Postgres.transaction():
            try:
                await Postgres.execute(
                    "DELETE FROM public.projects WHERE name = $1", self.name
                )
            finally:
                await Redis.delete("global", "project-list")
                await Redis.delete("project-anatomy", self.name)
                await Redis.delete("project-data", self.name)
                await Redis.delete("project-folders", self.name)
        return True

    async def promote(self) -> None:
        async with Postgres.transaction():
            logger.info(f"Promoting project skeleton {self.name} to full project")
            await Postgres.execute(f"CREATE SCHEMA project_{self.name}")

            # Create tables in the newly created schema
            await Postgres.execute(f"SET LOCAL search_path TO project_{self.name}")
            async with aiofiles.open("schemas/schema.project.sql") as f:
                schema_sql = await f.read()
            await Postgres.execute(schema_sql)

            await aux_table_update(self.name, "folder_types", self.folder_types)
            await aux_table_update(self.name, "task_types", self.task_types)
            await aux_table_update(self.name, "statuses", self.statuses)
            await aux_table_update(self.name, "tags", self.tags)
            await link_types_update(self.name, "link_types", self.link_types)

            self.data.pop("skeletonAnatomy", None)
            self.data.pop("isSkeleton", None)

            await self.save(promote=True)

            # Move thumbnail from project_thumbnails to project_<name>.thumbnails
            # does project thumbnail exist?

            r = await Postgres.fetchrow(
                "SELECT 1 FROM public.project_thumbnails WHERE project_name = $1",
                self.name,
            )
            if r:
                await Postgres.execute(
                    f"""
                        INSERT INTO project_{self.name}.thumbnails
                            (id, mime, data, meta, created_at)
                        SELECT
                            $1::UUID,
                            mime,
                            data,
                            meta,
                            created_at
                        FROM public.project_skeleton_thumbnails
                        WHERE project_name = $2
                    """,
                    "0" * 32,
                    self.name,
                )
                await Postgres.execute(
                    """
                    DELETE FROM public.project_skeleton_thumbnails
                    WHERE project_name = $1
                    """,
                    self.name,
                )

    @property
    def skeleton(self) -> bool:
        """Return True if the project is a skeleton."""
        return True
