from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType

BASE_GET_QUERY = """
    SELECT
        p.id as id,
        p.name as name,
        p.folder_id as folder_id,
        p.product_type as product_type,
        p.attrib as attrib,
        p.data as data,
        p.active as active,
        p.status as status,
        p.tags as tags,
        p.created_at as created_at,
        p.updated_at as updated_at,
        h.path as folder_path
    FROM project_{project_name}.products p
    JOIN project_{project_name}.hierarchy h ON p.folder_id = h.id
"""


class ProductEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "product"
    model = ModelSet("product", attribute_library["product"])
    base_get_query = BASE_GET_QUERY
    selector = "p.id"

    @staticmethod
    def preprocess_record(record: dict) -> dict:
        hierarchy_path = record.pop("folder_path", None)
        if hierarchy_path:
            hierarchy_path = hierarchy_path.strip("/")
            record["path"] = f"/{hierarchy_path}/{record['name']}"
        return record

    #
    # Access Control
    #

    async def pre_save(self, insert: bool) -> None:
        """Hook called before saving the entity to the database."""
        await Postgres.execute(
            """
            INSERT INTO public.product_types (name)
            VALUES ($1)
            ON CONFLICT DO NOTHING
            """,
            self.product_type,
        )

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "folder",
            self.folder_id,
            "publish",
        )

    async def ensure_update_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "folder",
            self.folder_id,
            "publish",
        )

    #
    # Properties
    #

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id  # type: ignore

    @folder_id.setter
    def folder_id(self, value: str):
        self._payload.folder_id = value  # type: ignore

    @property
    def parent_id(self) -> str:
        return self.folder_id

    @property
    def product_type(self) -> str:
        return self._payload.product_type  # type: ignore

    @product_type.setter
    def product_type(self, value: str):
        self._payload.product_type = value  # type: ignore
