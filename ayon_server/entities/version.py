from typing import NoReturn

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import (
    ConstraintViolationException,
    NotFoundException,
    ServiceUnavailableException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType


def version_name(version: int) -> str:
    if version < 0:
        return "HERO"
    return f"v{version:03d}"


class VersionEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "version"
    model = ModelSet("version", attribute_library["version"])

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        for_update: bool = False,
        **kwargs,
    ):
        """Return an entity instance based on its ID and a project name.

        Raise ValueError if project_name or base_id is not valid.
        Raise KeyError if the folder does not exists.

        Set for_update=True and pass a transaction to lock the row
        for update.
        """

        query = f"""
            SELECT
                v.id as id,
                v.version as version,
                v.product_id as product_id,
                v.task_id as task_id,
                v.thumbnail_id as thumbnail_id,
                v.author as author,

                v.attrib as attrib,
                v.data as data,
                v.active as active,
                v.status as status,
                v.tags as tags,
                v.created_at as created_at,
                v.updated_at as updated_at,

                p.name as product_name,
                h.path as folder_path

            FROM project_{project_name}.versions v
            JOIN project_{project_name}.products p ON v.product_id = p.id
            JOIN project_{project_name}.hierarchy h ON p.folder_id = h.id
            WHERE v.id=$1
            {'FOR UPDATE NOWAIT' if for_update else ''}
            """

        try:
            record = await Postgres.fetchrow(query, entity_id)
        except Postgres.UndefinedTableError as e:
            raise NotFoundException(
                f"Project '{project_name}' does not exist or is not initialized."
            ) from e
        except Postgres.LockNotAvailableError as e:
            raise ServiceUnavailableException(
                f"Entity {cls.entity_type} {entity_id} is locked for update."
            ) from e
        if record is None:
            raise NotFoundException(
                f"{cls.entity_type.capitalize()} {entity_id} "
                f"not found in project {project_name}"
            )

        record = dict(record)
        hierarchy_path = record.pop("folder_path", None)
        product_name = record.pop("product_name", None)
        if hierarchy_path and product_name:
            hierarchy_path = hierarchy_path.strip("/")
            vname = version_name(record["version"])
            record["path"] = f"/{hierarchy_path}/{product_name}/{vname}"

        return cls.from_record(project_name, record)

    async def pre_save(self, insert: bool) -> None:
        if self.version < 0:
            # Ensure there is no previous hero version
            res = await Postgres.fetchrow(
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
            if res is not None:
                raise ConstraintViolationException("Hero version already exists.")

        if self.task_id:
            # Bump the updated_at timestamp of the task
            # in order to re-fetch a new thumbnail
            await Postgres.execute(
                f"""
                UPDATE project_{self.project_name}.tasks
                SET updated_at = NOW()
                WHERE id = $1
                """,
                self.task_id,
            )

    @classmethod
    async def refresh_views(cls, project_name: str) -> None:
        """Refresh hierarchy materialized view on folder save."""

        await Postgres.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{project_name}.version_list
            """
        )

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
        return version_name(self.version)

    @name.setter
    def name(self, value: str) -> NoReturn:
        _ = value
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

    #
    # Read only properties
    #

    @property
    def path(self) -> str:
        return self._payload.path  # type: ignore
