from openpype.entities.core import ProjectLevelEntity, attribute_library
from openpype.entities.models import ModelSet
from openpype.lib.postgres import Postgres


class VersionEntity(ProjectLevelEntity):
    entity_type: str = "version"
    model = ModelSet("version", attribute_library["version"])

    @property
    def name(self):
        return f"v{self.version:03d}"

    async def commit(self, transaction=False):
        """Refresh hierarchy materialized view on folder save."""

        transaction = transaction or Postgres
        await transaction.execute(
            f"""
            DELETE FROM project_{self.project_name}.thumbnails
            WHERE id = $1
            """,
            self.id,
        )
        await transaction.execute(
            f"""
            REFRESH MATERIALIZED VIEW CONCURRENTLY
            project_{self.project_name}.version_list
            """
        )
