from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType

BASE_GET_QUERY = """
    SELECT
        entity.*,
        hierarchy.path as folder_path
    FROM project_{project_name}.products entity
    JOIN project_{project_name}.hierarchy hierarchy
        ON entity.folder_id = hierarchy.id
"""

# Product group used to live in `data.productGroup`. It is now a product
# attribute, but for backwards compatibility both are kept in sync.
PRODUCT_GROUP_KEY = "productGroup"


def sync_product_group_patch(patch: dict[str, Any]) -> None:
    """Mirror productGroup between attrib and data in a partial update (in place).

    When the attribute is patched, it is mirrored to data. Otherwise, when
    only data is patched, it is mirrored to the attribute. `None` means
    removal in both cases.
    """
    attrib = patch.get("attrib")
    data = patch.get("data")

    if isinstance(attrib, dict) and PRODUCT_GROUP_KEY in attrib:
        if data is None or isinstance(data, dict):
            value = attrib[PRODUCT_GROUP_KEY]
            patch["data"] = {**(data or {}), PRODUCT_GROUP_KEY: value}

    elif isinstance(data, dict) and PRODUCT_GROUP_KEY in data:
        value = data[PRODUCT_GROUP_KEY]
        if value is not None and not isinstance(value, str):
            return
        patch["attrib"] = {**(attrib or {}), PRODUCT_GROUP_KEY: value}


class ProductEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "product"
    model = ModelSet("product", attribute_library["product"])
    base_get_query = BASE_GET_QUERY

    @staticmethod
    def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
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

        if self.product_base_type is None:
            self.product_base_type = self.product_type

        self.sync_product_group()

        await Postgres.execute(
            """
            INSERT INTO public.product_types (name)
            VALUES ($1)
            ON CONFLICT DO NOTHING
            """,
            self.product_type,
        )

    def sync_product_group(self) -> None:
        """Keep attrib.productGroup and data.productGroup in sync.

        The attribute takes precedence. Partial updates are reconciled
        beforehand by `sync_product_group_patch`, so at this point a conflict
        only happens when a full payload sets both to different values.
        """
        data = self._payload.data  # type: ignore
        if data is None:
            data = self._payload.data = {}  # type: ignore

        attr_value = getattr(self.attrib, PRODUCT_GROUP_KEY, None)
        data_value = data.get(PRODUCT_GROUP_KEY)

        if attr_value is not None:
            data[PRODUCT_GROUP_KEY] = attr_value
        elif isinstance(data_value, str):
            setattr(self.attrib, PRODUCT_GROUP_KEY, data_value)
            if PRODUCT_GROUP_KEY not in self.own_attrib:
                self.own_attrib.append(PRODUCT_GROUP_KEY)

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

    @property
    def product_base_type(self) -> str | None:
        return self._payload.product_base_type  # type: ignore

    @product_base_type.setter
    def product_base_type(self, value: str | None):
        self._payload.product_base_type = value  # type: ignore
