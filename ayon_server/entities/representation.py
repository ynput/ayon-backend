from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType

from .version import version_name

BASE_GET_QUERY = """
    SELECT
        entity.id as id,
        entity.name as name,
        entity.version_id as version_id,
        entity.files as files,
        entity.attrib as attrib,
        entity.data as data,
        entity.traits as traits,
        entity.active as active,
        entity.status as status,
        entity.tags as tags,
        entity.created_at as created_at,
        entity.updated_at as updated_at,
        entity.created_by as created_by,
        entity.updated_by as updated_by,

        v.version as version,
        p.name as product_name,
        hierarchy.path as folder_path

    FROM project_{project_name}.representations entity
    JOIN project_{project_name}.versions v ON entity.version_id = v.id
    JOIN project_{project_name}.products p ON v.product_id = p.id
    JOIN project_{project_name}.hierarchy hierarchy ON p.folder_id = hierarchy.id
"""


class RepresentationEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "representation"
    model = ModelSet("representation", attribute_library["representation"])
    base_get_query = BASE_GET_QUERY

    @staticmethod
    def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
        hierarchy_path = record.pop("folder_path", None)
        product_name = record.pop("product_name", None)
        if hierarchy_path and product_name:
            hierarchy_path = hierarchy_path.strip("/")
            vname = version_name(record["version"])
            rname = record["name"]
            record["path"] = f"/{hierarchy_path}/{product_name}/{vname}/{rname}"
        return record

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "version",
            self.version_id,
            "publish",
        )

    async def ensure_update_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "version",
            self.version_id,
            "publish",
        )

    #
    # Properties
    #

    @property
    def version_id(self) -> str:
        return self._payload.version_id  # type: ignore

    @version_id.setter
    def version_id(self, value: str):
        self._payload.version_id = value  # type: ignore

    @property
    def parent_id(self) -> str:
        return self.version_id
