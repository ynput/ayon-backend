from typing import NoReturn

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import ConstraintViolationException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType


class VersionEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "version"
    model = ModelSet("version", attribute_library["version"])

    async def save(self, transaction=False) -> bool:
        """Save entity to database."""

        if self.version < 0:
            # Ensure there is no previous hero version
            res = await Postgres.fetch(
                f"""
                SELECT id FROM project_{self.project_name}.versions
                WHERE
                    version < 0
                AND id != $1
                AND product_id = $2
                """,
                self.id,
                self.product_id,
            )
            if res:
                raise ConstraintViolationException("Hero version already exists.")

        return await super().save(transaction=transaction)

    async def commit(self, transaction=False) -> None:
        """Refresh hierarchy materialized view on folder save."""

        transaction = transaction or Postgres
        await transaction.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.version_list
            """
        )

    async def ensure_create_access(self, user) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "product",
            self.product_id,
            "publish",
        )

    #
    # Properties
    #

    @property
    def name(self) -> str:
        return f"v{self.version:03d}"

    @name.setter
    def name(self, value) -> NoReturn:
        raise AttributeError("Cannot set name of version.")

    @property
    def version(self) -> int:
        return self._payload.version

    @version.setter
    def version(self, value: int) -> None:
        self._payload.version = value

    @property
    def product_id(self) -> str:
        return self._payload.product_id

    @product_id.setter
    def product_id(self, value: str) -> None:
        self._payload.product_id = value

    @property
    def parent_id(self) -> str:
        return self.product_id

    @property
    def task_id(self) -> str:
        return self._payload.task_id

    @task_id.setter
    def task_id(self, value: str) -> None:
        self._payload.task_id = value

    @property
    def thumbnail_id(self) -> str:
        return self._payload.thumbnail_id

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value

    @property
    def author(self) -> str:
        return self._payload.author
