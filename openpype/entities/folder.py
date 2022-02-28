from openpype.exceptions import RecordNotFoundException
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID

from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class FolderEntity(Entity):
    entity_type = EntityType.FOLDER
    entity_name = "folder"
    model = ModelSet("folder", attribute_library["folder"])

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

        if not (entity_id := EntityID.parse(entity_id)):
            raise ValueError(f"Invalid {cls.entity_name} ID specified")

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
                validate=False,
                **record,
            )
        raise RecordNotFoundException("Entity not found")

    async def commit(self, db=False):
        """Refresh hierarchy materialized view on folder save."""

        db = db or Postgres
        await Postgres.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.hierarchy
            """
        )
