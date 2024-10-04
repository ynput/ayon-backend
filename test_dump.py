import asyncio
import base64

from nxtools import logging

from ayon_server.entities.project import ProjectEntity
from ayon_server.helpers.deploy_project import create_project_from_anatomy
from ayon_server.helpers.dump_hierarchy import dump_hierarchy
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy
from ayon_server.utils import json_loads

SOURCE_PROJECT_NAME = "demo_commercial"
TARGET_PROJECT_NAME = "my_episodic_clone"
TARGET_PROJECT_CODE = "clne"


class DBPusher:
    buff_size = 1000
    statement = None
    buff = []
    total: int = 0

    def __init__(self):
        pass

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
        print(values)
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


async def main() -> None:
    """Main entry point for setup."""

    await ayon_init()

    project_list = await get_project_list()
    if TARGET_PROJECT_NAME in [project.name for project in project_list]:
        logging.debug(f"Project {TARGET_PROJECT_NAME} already exists, deleting it.")
        project = await ProjectEntity.load(TARGET_PROJECT_NAME)
        await project.delete()

    anatomy = Anatomy()
    await create_project_from_anatomy(TARGET_PROJECT_NAME, TARGET_PROJECT_CODE, anatomy)
    logging.debug(f"Project {TARGET_PROJECT_NAME} created.")

    _last_table_name: str | None = None
    pusher = DBPusher()

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute("SET CONSTRAINTS ALL DEFERRED")
        async for row in dump_hierarchy(SOURCE_PROJECT_NAME):
            table_name, entity_json = row.split(" ", 1)

            entity_payload = json_loads(entity_json)
            keys = entity_payload.keys()

            if table_name != _last_table_name:
                print("Switching from", _last_table_name, "to", table_name)
                await pusher.init(
                    conn, f"project_{TARGET_PROJECT_NAME}.{table_name}", keys
                )
                _last_table_name = table_name

            if table_name == "thumbnails":
                entity_payload["data"] = base64.b64decode(entity_payload["data"])

            await pusher.push(*entity_payload.values())

        await pusher.flush()

        # Flush everything
        await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        await conn.execute(
            f"REFRESH MATERIALIZED VIEW project_{TARGET_PROJECT_NAME}.hierarchy"
        )
        await rebuild_hierarchy_cache(TARGET_PROJECT_NAME, transaction=conn)
        await rebuild_inherited_attributes(TARGET_PROJECT_NAME, transaction=conn)


if __name__ == "__main__":
    asyncio.run(main())
