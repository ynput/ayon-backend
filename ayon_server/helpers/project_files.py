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


async def delete_project_file(project_name: str, file_id: str) -> None:
    """Delete a project file"""

    query = f"""
        DELETE FROM project_{project_name}.files
        WHERE id = $1
    """
    await Postgres.execute(query, file_id)

    file_id = str(file_id).replace("-", "")
    assert len(file_id) == 32

    query = f"""
        WITH updated_activities AS (
            SELECT
                id,
                jsonb_set(
                    data,
                    '{{files}}',
                    (SELECT jsonb_agg(elem)
                         FROM jsonb_array_elements(data->'files') elem
                         WHERE elem->>'id' != '{file_id}')
                ) AS new_data
            FROM
                project_{project_name}.activities
            WHERE
                data->'files' @> jsonb_build_array(
                    jsonb_build_object('id', '{file_id}')
                )
        )
        UPDATE project_{project_name}.activities
        SET data = updated_activities.new_data
        FROM updated_activities
        WHERE activities.id = updated_activities.id;
    """

    await Postgres.execute(query)

    path = id_to_path(project_name, file_id)
    if not os.path.exists(path):
        return

    try:
        os.remove(path)
    except Exception as e:
        logging.error(f"Failed to delete file {path}: {e}")

    directory = os.path.dirname(path)
    if not os.listdir(directory):
        try:
            os.rmdir(directory)
        except Exception as e:
            logging.error(f"Failed to delete directory {directory}: {e}")


async def delete_unused_files(project_name: str) -> None:
    """Delete files that are not referenced in any activity."""

    query = f"""
        SELECT id FROM project_{project_name}.files
        WHERE activity_id IS NULL
        AND updated_at < NOW() - INTERVAL '5 minutes'
    """

    async for row in Postgres.iterate(query):
        logging.debug(f"Deleting unused file {row['id']}")
        await delete_project_file(project_name, row["id"])
