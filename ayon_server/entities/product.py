from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType


class ProductEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "product"
    model = ModelSet("product", attribute_library["product"])

    #
    # Properties
    #

    async def pre_save(self, insert, transaction) -> None:
        """Hook called before saving the entity to the database."""
        await transaction.execute(
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

    @property
    def product_base_type(self) -> str:
        return self._payload.product_base_type  # type: ignore

    @product_base_type.setter
    def product_base_type(self, value: str):
        self._payload.product_base_type = value  # type: ignore
