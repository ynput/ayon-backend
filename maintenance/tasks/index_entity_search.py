from ayon_server.entity_search import backfill
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from maintenance.maintenance_task import ProjectMaintenanceTask


class IndexEntitySearch(ProjectMaintenanceTask):
    """Index what the background indexer missed: the initial backfill,
    saves lost on a restart and rows marked outdated (user renames)."""

    description = "Indexing entities for search"

    async def main(self, project_name: str) -> None:
        try:
            counts = await backfill(project_name)
        except Postgres.UndefinedTableError:
            return  # the project has no search table (yet)
        if indexed := {k: v for k, v in counts.items() if v}:
            logger.info(f"Indexed for search in {project_name}: {indexed}")
