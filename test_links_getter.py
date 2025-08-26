#!/usr/bin/env python3

import asyncio

from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres


async def main():
    await ayon_init()
    all_entity_ids = []

    async with Postgres.transaction():
        await Postgres.set_project_schema("projectmonaco")

        query = """
            SELECT id FROM folders
            UNION
            SELECT id FROM versions
            UNION
            SELECT id FROM tasks
        """
        stmt = await Postgres.prepare(query)
        async for row in stmt.cursor():
            all_entity_ids.append(row["id"])

    print(f"Found {len(all_entity_ids)} entity IDs in the project.")


if __name__ == "__main__":
    asyncio.run(main())
