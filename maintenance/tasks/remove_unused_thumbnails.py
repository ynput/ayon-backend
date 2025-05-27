from ayon_server.files import Storages
from ayon_server.lib.postgres import Postgres
from maintenance.maintenance_task import ProjectMaintenanceTask


async def clear_thumbnails(project_name: str) -> None:
    """Purge unused thumbnails from the database.

    Locate thumbnails not referenced by any folder, version or workfile
    and delete them.

    Delete only thumbnails older than 24 hours.
    """

    # keep this outside the query - it's easier to debug this way
    older_cond = "created_at < 'yesterday'::timestamp AND"
    # older_cond = ""

    query = f"""
        DELETE FROM project_{project_name}.thumbnails t
        WHERE {older_cond} NOT EXISTS (
            SELECT 1 FROM project_{project_name}.folders WHERE thumbnail_id = t.id
        ) AND NOT EXISTS (
            SELECT 1 FROM project_{project_name}.tasks WHERE thumbnail_id = t.id
        ) AND NOT EXISTS (
            SELECT 1 FROM project_{project_name}.versions WHERE thumbnail_id = t.id
        ) AND NOT EXISTS (
            SELECT 1 FROM project_{project_name}.workfiles WHERE thumbnail_id = t.id
        )
        RETURNING id
    """

    storage = await Storages.project(project_name)
    async for row in Postgres.iterate(query):
        await storage.delete_thumbnail(row["id"])


class RemoveUnusedThumbnails(ProjectMaintenanceTask):
    description = "Removing unused thumbnails"

    async def main(self, project_name: str):
        storage = await Storages.project(project_name)
        await storage.delete_unused_files()
