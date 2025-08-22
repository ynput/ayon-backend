import sqlite3

from ayon_server.cli import app
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from nxtools import logging


async def cleanup_project_files(project_name: str, *, dry_run: bool) -> None:
    logging.info(f"Cleaning up files for project: {project_name}")
    storage = await Storages.project(project_name)

    # Create an SQLite database in memory
    # to store the list of files on the storage

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE files (
            file_id TEXT PRIMARY KEY,
            storage BOOLEAN DEFAULT 0,
            database BOOLEAN DEFAULT 0
        )
    """)

    # Retrieve the list of files on the storage
    # and store them in the database

    storage = await Storages.project(project_name)
    async for _rec in storage.list_files():
        cursor.execute(
            "INSERT OR IGNORE INTO files (file_id, storage) VALUES (?, ?)", (_rec, True)
        )

    conn.commit()

    # Retrieve the list of file IDs from the database
    # Those are files ayon is aware of

    query = f"SELECT id FROM project_{project_name}.files"
    async for row in Postgres.iterate(query):
        file_id = row["id"]
        cursor.execute(
            "INSERT OR IGNORE INTO files (file_id, database) VALUES (?, ?)",
            (file_id, True),
        )
        cursor.execute(
            "UPDATE files SET database = ? WHERE file_id = ?", (True, file_id)
        )

    conn.commit()

    # Now we have a list of file IDs from the storage and the database
    # let's compare them to find the files that are missing from either
    # the storage or the database

    cursor.execute(
        """
        SELECT file_id, storage, database FROM files
        WHERE storage = 0 OR database = 0
        """
    )
    for row in cursor.fetchall():
        file_id, is_on_storage, is_in_database = row
        if not is_on_storage:
            logging.warning(f"{file_id} is missing from storage")
            if not dry_run:
                await storage.unlink(file_id)

        if not is_in_database:
            logging.info(f"{file_id} is missing from database")

    # Close the SQLite connection
    conn.close()


@app.command()
async def file_cleanup(
    project_name: str | None = None,
    dry_run: bool = False,
) -> None:
    await ayon_init()

    projects = await get_project_list()

    if project_name is None:
        for project in projects:
            await cleanup_project_files(project.name, dry_run=dry_run)
    else:
        await cleanup_project_files(project_name, dry_run=dry_run)
