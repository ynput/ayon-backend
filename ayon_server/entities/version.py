from typing import NoReturn

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import ConstraintViolationException
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.types import ProjectLevelEntityType


class VersionEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "version"
    model = ModelSet("version", attribute_library["version"])

    async def save(self, transaction: Connection | None = None) -> None:
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

        await super().save(transaction=transaction)

    async def commit(self, transaction=None) -> None:
        """Refresh hierarchy materialized view on folder save."""

        async def _commit(conn):
            await conn.execute(
                f"""
                REFRESH MATERIALIZED VIEW CONCURRENTLY
                project_{self.project_name}.version_list
                """
            )

        if transaction:
            await _commit(transaction)
        else:
            async with Postgres.acquire() as conn, conn.transaction():
                await _commit(conn)

    async def ensure_create_access(self, user, **kwargs) -> None:
        if user.is_manager:
            return

        await ensure_entity_access(
            user,
            self.project_name,
            "product",
            self.product_id,
            "publish",
        )

    async def ensure_update_access(self, user, **kwargs) -> None:
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
        return self._payload.version  # type: ignore

    @version.setter
    def version(self, value: int) -> None:
        self._payload.version = value  # type: ignore

    @property
    def product_id(self) -> str:
        return self._payload.product_id  # type: ignore

    @product_id.setter
    def product_id(self, value: str) -> None:
        self._payload.product_id = value  # type: ignore

    @property
    def parent_id(self) -> str:
        return self.product_id

    @property
    def task_id(self) -> str:
        return self._payload.task_id  # type: ignore

    @task_id.setter
    def task_id(self, value: str) -> None:
        self._payload.task_id = value  # type: ignore

    @property
    def thumbnail_id(self) -> str:
        return self._payload.thumbnail_id  # type: ignore

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value  # type: ignore

    @property
    def author(self) -> str:
        return self._payload.author  # type: ignore
