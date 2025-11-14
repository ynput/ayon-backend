from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import AyonException
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType

BASE_GET_QUERY = """
    SELECT
        entity.id as id,
        entity.name as name,
        entity.label as label,
        entity.task_type as task_type,
        entity.thumbnail_id as thumbnail_id,
        entity.assignees as assignees,
        entity.folder_id as folder_id,
        entity.attrib as attrib,
        entity.data as data,
        entity.active as active,
        entity.created_at as created_at,
        entity.updated_at as updated_at,
        entity.created_by as created_by,
        entity.updated_by as updated_by,
        entity.status as status,
        entity.tags as tags,
        ia.attrib AS inherited_attrib,
        hierarchy.path as folder_path
    FROM project_{project_name}.tasks as entity
    JOIN project_{project_name}.hierarchy as hierarchy
        ON entity.folder_id = hierarchy.id
    LEFT JOIN
        project_{project_name}.exported_attributes as ia
        ON entity.folder_id = ia.folder_id
"""


class TaskEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "task"
    model = ModelSet("task", attribute_library["task"])
    base_get_query = BASE_GET_QUERY

    @staticmethod
    def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
        attrib: dict[str, Any] = {}
        inhereited_attrib: dict[str, Any] = {}
        if (ia := record["inherited_attrib"]) is not None:
            for key, value in ia.items():
                if key in attribute_library.inheritable_attributes():
                    attrib[key] = value
                    inhereited_attrib[key] = value
        elif record["parent_id"] is not None:
            logger.warning(
                f"Task {record['id']} does not have inherited attributes."
                "this shouldn't happen"
            )
        attrib |= record["attrib"]
        payload = {**record, "attrib": attrib, "inherited_attrib": inhereited_attrib}

        folder_path = payload.pop("folder_path", None)
        folder_path = folder_path.strip("/")
        payload["path"] = f"/{folder_path}/{payload['name']}"
        return payload

    async def save(self, *args, auto_commit: bool = True, **kwargs) -> None:
        async with Postgres.transaction():
            if self.task_type is None:
                res = await Postgres.fetch(
                    f"""
                    SELECT name from project_{self.project_name}.task_types
                    ORDER BY position ASC LIMIT 1
                    """
                )
                if not res:
                    raise AyonException("No task types defined")
                self.task_type = res[0]["name"]
            await super().save(auto_commit=auto_commit)

    @classmethod
    async def refresh_views(cls, project_name: str) -> None:
        await rebuild_hierarchy_cache(project_name)

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "folder",
            self.folder_id,
            "create",
        )

    #
    # Properties
    #

    @property
    def label(self) -> str | None:
        """Return the label of the task."""
        return self._payload.label  # type: ignore

    @label.setter
    def label(self, value: str) -> None:
        """Set the label of the task."""
        self._payload.label = value  # type: ignore

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id  # type: ignore

    @folder_id.setter
    def folder_id(self, value: str) -> None:
        self._payload.folder_id = value  # type: ignore

    @property
    def parent_id(self) -> str:
        return self.folder_id

    @property
    def task_type(self) -> str:
        return self._payload.task_type  # type: ignore

    @task_type.setter
    def task_type(self, value: str) -> None:
        self._payload.task_type = value  # type: ignore

    @property
    def assignees(self) -> list[str]:
        return self._payload.assignees  # type: ignore

    @assignees.setter
    def assignees(self, value: list[str]) -> None:
        self._payload.assignees = value  # type: ignore

    @property
    def entity_subtype(self) -> str:
        return self.task_type

    @property
    def thumbnail_id(self) -> str | None:
        return self._payload.thumbnail_id  # type: ignore

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value  # type: ignore

    #
    # Read only properties
    #

    @property
    def path(self) -> str:
        return self._payload.path  # type: ignore
