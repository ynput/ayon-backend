from openpype.lib.postgres import Postgres

from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class FolderEntity(Entity):
    entity_type = EntityType.FOLDER
    entity_name = "folder"
    model = ModelSet("folder", attribute_library["folder"])

    async def commit(self, db=False):
        """Refresh hierarchy materialized view on folder save."""

        db = db or Postgres
        await Postgres.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.hierarchy
            """
        )
