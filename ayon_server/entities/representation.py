from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.common import query_entity_data
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType

from .version import version_name


class RepresentationEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "representation"
    model = ModelSet("representation", attribute_library["representation"])

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        for_update: bool = False,
        **kwargs,
    ):
        query = f"""
            SELECT
                r.id as id,
                r.name as name,
                r.version_id as version_id,
                r.files as files,
                r.attrib as attrib,
                r.data as data,
                r.traits as traits,
                r.active as active,
                r.status as status,
                r.tags as tags,
                r.created_by as created_by,
                r.updated_by as updated_by,
                r.created_at as created_at,
                r.updated_at as updated_at,

                v.version as version,
                p.name as product_name,
                h.path as folder_path

            FROM project_{project_name}.representations r
            JOIN project_{project_name}.versions v ON r.version_id = v.id
            JOIN project_{project_name}.products p ON v.product_id = p.id
            JOIN project_{project_name}.hierarchy h ON p.folder_id = h.id
            WHERE r.id=$1
            {'FOR UPDATE NOWAIT' if for_update else ''}
            """

        record = await query_entity_data(query, entity_id)

        hierarchy_path = record.pop("folder_path", None)
        product_name = record.pop("product_name", None)
        if hierarchy_path and product_name:
            hierarchy_path = hierarchy_path.strip("/")
            vname = version_name(record["version"])
            rname = record["name"]
            record["path"] = f"/{hierarchy_path}/{product_name}/{vname}/{rname}"

        return cls.from_record(project_name, record)

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
