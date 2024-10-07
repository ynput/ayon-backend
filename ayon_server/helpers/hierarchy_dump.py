import asyncio
import os
import tempfile
import zipfile
from collections import deque
from typing import Any

import aiofiles
import aioshutil

from ayon_server.files import Storages
from ayon_server.helpers.download import download_file
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import batched, json_dumps
from ayon_server.version import __version__


def _make_zip(source: str, destination: str) -> None:
    """Create a zip file from a directory"""

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=source)
                zipf.write(file_path, arcname)


async def make_zip(source: str, destination: str) -> None:
    """Create a zip file from a directory using a threadpool"""
    await asyncio.to_thread(_make_zip, source, destination)


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


async def copy_project_file(project_name: str, file_id: str, target_dir: str) -> None:
    storage = await Storages.project(project_name)
    os.makedirs(target_dir, exist_ok=True)
    if storage.storage_type == "local":
        path = await storage.get_path(file_id)
        target_path = os.path.join(target_dir, file_id)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        await aioshutil.copyfile(path, target_path)
    elif storage.storage_type == "s3":
        url = await storage.get_signed_url(file_id)
        target_path = os.path.join(target_dir, file_id)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        await download_file(url, target_path)


async def dump_hierarchy_to_dir(
    temp_dir: str,
    project_name: str,
    *,
    root: str | None = None,
    with_activities: bool = False,
):
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    else:
        # clear the directory
        for file in os.listdir(temp_dir):
            path = os.path.join(temp_dir, file)
            if os.path.isdir(path):
                await aioshutil.rmtree(path)  # type: ignore
            else:
                os.remove(path)

    manifest: dict[str, Any] = {
        "ayonVersion": __version__,
        "rootFolder": root,
    }

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

    for batch in batched(required_thumbnails, 100):
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

    # Do not include thumbnails directory if it is empty
    if not os.listdir(thumb_dir):
        os.rmdir(thumb_dir)

    if with_activities:
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

        files_dir = os.path.join(temp_dir, "files")
        async with aiofiles.open(f"{temp_dir}/files.json", "w") as f:
            q = f"SELECT * FROM project_{project_name}.files"
            async for row in Postgres.iterate(q):
                if row["activity_id"] not in copied_activities:
                    continue
                json = json_dumps(dict(row))
                await f.write(json + "\n")
                await copy_project_file(project_name, row["id"], files_dir)

    async with aiofiles.open(f"{temp_dir}/manifest.json", "w") as f:
        await f.write(json_dumps(manifest))


async def hierarchy_dump(
    target_zip_path: str,
    project_name: str,
    *,
    root: str | None = None,
    with_activities: bool = False,
):
    temp_dir = tempfile.mkdtemp(dir="/storage/")
    try:
        await dump_hierarchy_to_dir(
            temp_dir,
            project_name,
            root=root,
            with_activities=with_activities,
        )
        await make_zip(temp_dir, target_zip_path)
    finally:
        await aioshutil.rmtree(temp_dir)  # type: ignore
