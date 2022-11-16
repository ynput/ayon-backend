import time

from openpype.lib.postgres import Postgres


async def clear_thumbnails(project_name: str):
    """Purge unused thumbnails from the database.

    Locate thumbnails not referenced by any folder, version or workfile
    and delete them.

    Delete only thumbnails older than 24 hours.
    """

    query = f"""

    DELETE FROM project_{project_name}.thumbnails
        WHERE created_at < $1
        AND id NOT IN (
            SELECT thumbnail_id FROM project_{project_name}.folders
            UNION
            SELECT thumbnail_id FROM project_{project_name}.versions
            UNION
            SELECT thumbnail_id FROM project_{project_name}.workfiles
        )
    """

    await Postgres.execute(query, time.time() - 24 * 3600)
