from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import (
    AyonException,
    NotFoundException,
    ServiceUnavailableException,
)
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import EntityID


class TaskEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "task"
    model = ModelSet("task", attribute_library["task"])

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        for_update=False,
        **kwargs: Any,
    ) -> "TaskEntity":
        """Load a task from the database by its project name and ID.

        This is reimplemented, because we need to select
        attributes inherited from the parent folder.
        """

        if EntityID.parse(entity_id) is None:
            raise ValueError(f"Invalid {cls.entity_type} ID specified")

        query = f"""
            SELECT
                t.id as id,
                t.name as name,
                t.label as label,
                t.task_type as task_type,
                t.thumbnail_id as thumbnail_id,
                t.assignees as assignees,
                t.folder_id as folder_id,
                t.attrib as attrib,
                t.data as data,
                t.active as active,
                t.created_at as created_at,
                t.updated_at as updated_at,
                t.status as status,
                t.tags as tags,
                ia.attrib AS inherited_attrib
            FROM project_{project_name}.tasks as t
            LEFT JOIN
                project_{project_name}.exported_attributes as ia
                ON t.folder_id = ia.folder_id
            WHERE t.id=$1
            {'FOR UPDATE OF t NOWAIT' if for_update else ''}
            """

        try:
            record = await Postgres.fetchrow(query, entity_id)
        except Postgres.UndefinedTableError:
            raise NotFoundException(f"Project {project_name} not found")
        except Postgres.LockNotAvailableError:
            raise ServiceUnavailableException(
                f"Task {entity_id} is locked by another operation"
            )

        if record is None:
            raise NotFoundException(
                f"Task {entity_id} not found in project {project_name}"
            )

        attrib: dict[str, Any] = {}
        if (ia := record["inherited_attrib"]) is not None:
            for key, value in ia.items():
                if key in attribute_library.inheritable_attributes():
                    attrib[key] = value
        elif record["parent_id"] is not None:
            logger.warning(
                f"Task {record['id']} does not have inherited attributes."
                "this shouldn't happen"
            )
        attrib |= record["attrib"]
        own_attrib = list(record["attrib"].keys())
        payload = {**record, "attrib": attrib}
        return cls.from_record(
            project_name=project_name,
            payload=payload,
            own_attrib=own_attrib,
        )

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
