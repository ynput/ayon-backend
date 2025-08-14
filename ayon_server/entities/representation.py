from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.exceptions import NotFoundException, ServiceUnavailableException
from ayon_server.lib.postgres import Postgres
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
