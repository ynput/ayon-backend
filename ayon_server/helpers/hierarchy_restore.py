import asyncio
import os
import tempfile
import zipfile
from typing import Any

import aiofiles
from nxtools import logging

from ayon_server.files import Storages
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.lib.postgres import Connection, Postgres
from ayon_server.utils import batched, create_uuid, json_loads


def _unzip_to_dir(zip_file: str, target_dir: str):
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(target_dir)


async def unzip_to_dir(zip_file: str, target_dir: str):
    await asyncio.to_thread(_unzip_to_dir, zip_file, target_dir)


class Reindexer:
    def __init__(self):
        self.data: dict[str, str] = {}

    def __call__(self, id: str):
        new_id = self.data.get(id)
        if new_id is None:
            new_id = create_uuid()
            self.data[id] = new_id
        return new_id


class DBPusher:
    buff_size = 1000
    statement = None
    buff: list[tuple[Any]] = []
    total: int = 0
    table_name: str | None = None

    async def init(self, connection, table_name: str, keys: list[str]):
        logging.debug(f"Initializing pusher for {table_name}")
        await self.flush()
        self.table_name = table_name
        self.total = 0
        self.keys = keys
        if not self.keys:
            raise ValueError("Keys list cannot be empty")

        # coma separated list of keys
        _k = ", ".join(keys)

        # $1, $2, $3, ...
        _v = ", ".join([f"${i+1}" for i in range(len(keys))])

        self.buff = []
        self.base_query = f"INSERT INTO {table_name} ({_k}) VALUES ({_v})"
        self.statement = await connection.prepare(self.base_query)

    async def push(self, *values):
        if not self.statement:
            raise ValueError("Statement not initialized")
        if self.buff_size == len(self.buff):
            await self.flush()
        self.buff.append(values)

    async def flush(self):
        if not self.statement:
            return
        if not self.buff:
            return
        await self.statement.executemany(self.buff)
        self.total += len(self.buff)
        logging.debug(f"Pushed {self.total} records to {self.table_name}")
        self.buff = []


#
# Import stuff
#

MIME_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


async def import_thumbnails(project_name: str, thumb_dir: str, conn: Connection):
    query = f"""
        INSERT INTO project_{project_name}.thumbnails (id, mime, data, meta)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO NOTHING
    """

    i = 0
    stmt = await conn.prepare(query)
    for files in batched(os.listdir(thumb_dir), 50):
        batch = []
        for file in files:
            thumb_id, ext = file.split(".")
            ext = ext.lower().strip(".")
            if ext not in MIME_MAP:
                continue
            size = os.path.getsize(f"{thumb_dir}/{file}")
            mime = MIME_MAP[ext]
            meta = {
                "originalSize": size,
                "thumbnailSize": size,
                "mime": mime,
            }

            with open(f"{thumb_dir}/{file}", "rb") as f:
                data = f.read()
            i += 1
            batch.append((thumb_id, "image/jpeg", data, meta))

        await stmt.executemany(batch)
        logging.info(f"Imported {i} thumbnails")


async def import_entities(
    project_name: str,
    dump_dir: str,
    conn: Connection,
    *,
    reindex_entities: bool = False,
    root: str | None = None,
):
    manifest_file = f"{dump_dir}/manifest.json"
    manifest = json_loads(open(manifest_file).read())
    source_root = manifest.get("rootFolder")

    reindex = Reindexer()

    for table in ["folders", "tasks", "activities", "activity_references", "files"]:
        dump_file = f"{dump_dir}/{table}.json"
        if not os.path.exists(dump_file):
            continue

        pusher = DBPusher()

        async with aiofiles.open(dump_file) as f:
            async for line in f:
                data = json_loads(line)
                data.pop("creation_order", None)

                top_level = False
                if table == "folders" and data["parent_id"] == source_root:
                    print("Assign", data["name"], "to root", root)
                    data["parent_id"] = root
                    top_level = True

                if reindex_entities:
                    # We do not reindex thumbnails! we can reuse them
                    # even within the same project
                    rkeys = ["id", "folder_id", "entity_id", "activity_id", "file_id"]
                    if not top_level:
                        rkeys.append("parent_id")
                    for k in rkeys:
                        if k in data:
                            old_id = data[k]
                            new_id = reindex(old_id)
                            data[k] = new_id

                    if table == "activities":
                        adata = data["data"]
                        if "origin" in adata:
                            adata["origin"]["id"] = reindex(adata["origin"]["id"])
                        files = adata.get("files", [])
                        if files:
                            nfiles = []
                            for file in files:
                                file["id"] = reindex(file["id"])
                                nfiles.append(file)
                            adata["files"] = nfiles
                        data["data"] = adata

                if not pusher.table_name:
                    keys = list(data.keys())
                    await pusher.init(conn, f"project_{project_name}.{table}", keys)

                await pusher.push(*[data[k] for k in pusher.keys])

        await pusher.flush()

    # Flush everything
    # The order is important! We need to rebuild inherited
    # attributes before hierarchy cache!
    await conn.execute(f"REFRESH MATERIALIZED VIEW project_{project_name}.hierarchy")
    await rebuild_inherited_attributes(project_name, transaction=conn)
    await rebuild_hierarchy_cache(project_name, transaction=conn)

    if os.path.isdir(f"{dump_dir}/files"):
        storage = await Storages.project(project_name)
        for file_id in os.listdir(f"{dump_dir}/files"):
            file_path = f"{dump_dir}/files/{file_id}"
            if reindex_entities:
                new_id = reindex(file_id)
            else:
                new_id = file_id
            await storage.upload_file(new_id, file_path)


#
# Restore stuff
#


async def restore_from_dump_directory(
    project_name: str,
    dump_dir: str,
    *,
    reindex_entities: bool = False,
    root: str | None = None,
):
    print(f"Restoring hierarchy to {project_name} from {dump_dir}")
    print(f"Reindex entities: {reindex_entities}")
    print(f"Root folder: {root}")

    async with Postgres.acquire() as conn, conn.transaction():
        # we need to import thumbnails first as entities might reference them
        # don't worry if they're there as we're using ON CONFLICT DO NOTHING
        # also don't worry if they're not used as the thumbnails_cleaner
        # will take care of them eventually
        thumb_dir = f"{dump_dir}/thumbnails"
        if os.path.isdir(thumb_dir) and os.listdir(thumb_dir):
            await import_thumbnails(project_name, thumb_dir, conn)

        await import_entities(
            project_name,
            dump_dir,
            conn,
            reindex_entities=reindex_entities,
            root=root,
        )


async def hierarchy_restore(
    project_name: str,
    dump_file: str,
    *,
    reindex_entities: bool = False,
    root: str | None = None,
):
    """
    project_name:
        The name of the project where the hierarchy should be imported.
        The project MUST exist in the database.

    dump_file:
        The path to the zip file containing the hierarchy dump.

    reindex_entities:
        change the id of the entities to new ones.
        set to true when you want to import the hierarchy to the same project.

    root:
        The root folder id where the hierarchy should be imported.
        The folder MUST exist in the project. Use none to import to root
    """

    with tempfile.TemporaryDirectory(dir="/storage/") as temp_dir:
        await unzip_to_dir(dump_file, temp_dir)
        await restore_from_dump_directory(
            project_name,
            temp_dir,
            reindex_entities=reindex_entities,
            root=root,
        )
