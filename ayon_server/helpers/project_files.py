import os

from nxtools import logging

from ayon_server.config import ayonconfig
from ayon_server.lib.postgres import Postgres


def id_to_path(project_name: str, file_id: str) -> str:
    file_id = file_id.replace("-", "")
    assert len(file_id) == 32
    fgroup = file_id[:2]
    return os.path.join(
        ayonconfig.project_data_dir,
        project_name,
        "uploads",
        fgroup,
        file_id,
    )


async def delete_unused_files(project_name: str) -> None:
    """Delete files that are not referenced in any activity."""

    query = f"""
        SELECT id FROM project_{project_name}.files
        WHERE activity_id IS NULL
        AND updated_at < NOW() - INTERVAL '5 minutes'
    """

    async for row in Postgres.iterate(query):
        logging.debug(f"Deleting unused file {row['id']}")
        query = f"""
            DELETE FROM project_{project_name}.files
            WHERE id = $1
        """
        await Postgres.execute(query, row["id"])

        path = id_to_path(project_name, row["id"])
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.error(f"Failed to delete file {path}: {e}")
