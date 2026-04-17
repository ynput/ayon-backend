from datetime import datetime
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool, dict_exclude

from .project import ProjectEntity


class ProjectSkeletonEntity(ProjectEntity):
    is_skeleton: bool = True

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

    async def save(self) -> bool:
        assert self.folder_types, "Project must have at least one folder type"
        assert self.task_types, "Project must have at least one task type"
        assert self.statuses, "Project must have at least one status"

        self.config.pop("productTypes", None)  # legacy
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
                        ],
                    ),
                )
            )
        return True
