from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID


class FolderEntity(ProjectLevelEntity):
    entity_type: str = "folder"
    model: ModelSet = ModelSet("folder", attribute_library["folder"])

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        transaction=None,
        for_update=False,
    ) -> "FolderEntity":
        """Load a folder from the database by its project name and IDself.

        This is reimplemented, because we need to select dynamic
        attribute hierarchy.path along with the base data.
        """
        project_name = project_name.lower()

        if EntityID.parse(entity_id) is None:
            raise ValueError(f"Invalid {cls.entity_type} ID specified")

        query = f"""
            SELECT
                f.id as id,
                f.name as name,
                f.folder_type as folder_type,
                f.parent_id as parent_id,
                f.thumbnail_id as thumbnail_id,
                f.attrib as attrib,
                f.data as data,
                f.active as active,
                f.created_at as created_at,
                f.updated_at as updated_at,
                h.path as path
            FROM project_{project_name}.folders as f
            INNER JOIN
                project_{project_name}.hierarchy as h
                ON f.id = h.id
            WHERE f.id=$1
            {'FOR UPDATE OF f'
                if transaction and for_update else ''
            }
            """

        async for record in Postgres.iterate(query, entity_id):
            return cls.from_record(
                project_name=project_name,
                payload=record,
                validate=False,
            )
        raise NotFoundException("Entity not found")

    async def commit(self, db=False):
        """Refresh hierarchy materialized view on folder save."""

        db = db or Postgres
        await db.execute(
            f"""
            DELETE FROM project_{self.project_name}.thumbnails
            WHERE id = $1
            """,
            self.id,
        )
        await db.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.hierarchy
            """
        )

    #
    # Properties
    #

    @property
    def parent_id(self) -> str:
        return self._payload.parent_id

    @parent_id.setter
    def parent_id(self, value: str) -> None:
        self._payload.parent_id = value

    @property
    def folder_type(self) -> str:
        return self._payload.folder_type

    @folder_type.setter
    def folder_type(self, value: str) -> None:
        self._payload.folder_type = value

    @property
    def thumbnail_id(self) -> str:
        return self._payload.thumbnail_id

    @thumbnail_id.setter
    def thumbnail_id(self, value: str) -> None:
        self._payload.thumbnail_id = value

    #
    # Read only properties
    #

    @property
    def path(self) -> str:
        return self._payload.path
