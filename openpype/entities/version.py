from openpype.lib.postgres import Postgres

from .common import Entity, EntityType, attribute_library
from .models import ModelSet


class VersionEntity(Entity):
    entity_type = EntityType.VERSION
    entity_name = 'version'
    model = ModelSet("version", attribute_library["version"])

    @property
    def name(self):
        return f"v{self.version:03d}"

    async def commit(self, transaction=False):
        """Refresh hierarchy materialized view on folder save."""

        transaction = transaction or Postgres
        await Postgres.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.version_list
            """
        )
