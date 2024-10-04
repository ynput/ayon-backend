import itertools
import os
import tempfile
from collections import deque

import aiofiles
import aioshutil

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import json_dumps


async def make_zip(source: str, destination: str) -> None:
    base_name = ".".join(destination.split(".")[:-1])
    format = destination.split(".")[-1]
    root_dir = os.path.dirname(source)
    base_dir = os.path.basename(source.strip(os.sep))
    await aioshutil.make_archive(base_name, format, root_dir, base_dir)


async def get_subfolders_of(project_name: str, root: str | None = None):
    if root is None:
        cond = "parent_id IS NULL"
    else:
        cond = f"parent_id = '{root}'"
    query = f"""
    SELECT *,
    EXISTS (
        SELECT 1 FROM project_{project_name}.folders AS subfolders
        WHERE subfolders.parent_id = folders.id
    ) AS has_children
    FROM project_{project_name}.folders WHERE {cond}
    """

    async for row in Postgres.iterate(query):
        yield dict(row)


async def dump_hierarchy_to_dir(
    temp_dir: str,
    project_name: str,
    root: str | None = None,
):
    temp_dir = "/storage/hdump"

    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    else:
        # clear the directory
        for file in os.listdir(temp_dir):
            path = os.path.join(temp_dir, file)
            if os.path.isdir(path):
                await aioshutil.rmtree(path)
            else:
                os.remove(path)

    # Dump folders

    copied_entities = set()
    required_thumbnails = set()

    async with aiofiles.open(f"{temp_dir}/folders.json", "w") as f:
        queue = deque([root])
        while queue:
            current_parent = queue.popleft()
            async for folder in get_subfolders_of(project_name, current_parent):
                if folder.pop("has_children", None):
                    queue.append(folder["id"])

                copied_entities.add(folder["id"])
                if folder["thumbnail_id"]:
                    required_thumbnails.add(folder["thumbnail_id"])
                json = json_dumps(folder)
                await f.write(json + "\n")

    async with aiofiles.open(f"{temp_dir}/tasks.json", "w") as f:
        q = f"SELECT * FROM project_{project_name}.tasks"
        async for row in Postgres.iterate(q):
            if row["folder_id"] not in copied_entities:
                continue
            if row["thumbnail_id"]:
                required_thumbnails.add(row["thumbnail_id"])
            json = json_dumps(dict(row))
            await f.write(json + "\n")

    thumb_dir = os.path.join(temp_dir, "thumbnails")
    if not os.path.exists(thumb_dir):
        os.makedirs(thumb_dir)

    for batch in itertools.batched(required_thumbnails, 100):
        q = f"""
            SELECT id, mime, data
            FROM project_{project_name}.thumbnails
            WHERE id = ANY($1)
        """
        async for row in Postgres.iterate(q, batch):
            mime = row["mime"]

        ext = mime.split("/")[1]
        async with aiofiles.open(f"{thumb_dir}/{row['id']}.{ext}", "wb") as f:
            await f.write(row["data"])

    copied_activities = set()

    async with aiofiles.open(f"{temp_dir}/activities.json", "w") as f:
        q = f"""
            SELECT * FROM project_{project_name}.activities
            WHERE data->'origin'->>'type' IN ('folder', 'task')
        """
        async for row in Postgres.iterate(q):
            if row["data"]["origin"]["id"] not in copied_entities:
                continue
            copied_activities.add(row["id"])
            json = json_dumps(dict(row))
            await f.write(json + "\n")

    async with aiofiles.open(f"{temp_dir}/activity_references.json", "w") as f:
        q = f"SELECT * FROM project_{project_name}.activity_references"
        async for row in Postgres.iterate(q):
            if row["activity_id"] not in copied_activities:
                continue
            copied_entities.add(row["id"])
            json = json_dumps(dict(row))
            await f.write(json + "\n")


async def dump_hierarchy(
    target_zip_path: str,
    project_name: str,
    root: str | None = None,
):
    temp_dir = tempfile.mkdtemp()
    try:
        await dump_hierarchy_to_dir(temp_dir, project_name, root)
        await make_zip(temp_dir, target_zip_path)
    finally:
        await aioshutil.rmtree(temp_dir)
