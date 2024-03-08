from typing import Any

from nxtools import logging

from ayon_server.entities.core import attribute_library
from ayon_server.lib.postgres import Postgres


async def rebuild_inherited_attributes(project_name: str, pattr: dict[str, Any]):
    """Rebuild inherited attributes for all objects in the project."""
    logging.debug("Rebuilding inherited attributes for", project_name)

    project_attrib = pattr.copy()
    async with Postgres.acquire() as conn, conn.transaction():
        # Filter out non-inheritable and non-folder attributes
        for attr_type in attribute_library["folder"]:
            if attr_type["name"] not in project_attrib:
                continue
            if not attr_type.get("inherit", True):
                del project_attrib[attr_type["name"]]

        st_crawl = await conn.prepare(
            f"""
            SELECT h.id, h.path, f.attrib as own, e.attrib as exported
            FROM project_{project_name}.hierarchy h
            INNER JOIN project_{project_name}.folders f
            ON h.id = f.id
            LEFT JOIN project_{project_name}.exported_attributes e
            ON h.id = e.folder_id
            ORDER BY h.path ASC
            """
        )

        st_upsert = await conn.prepare(
            f"""
             INSERT INTO project_{project_name}.exported_attributes
                 (folder_id, path, attrib)
             VALUES
                ($1, $2, $3)
             ON CONFLICT (folder_id)
             DO UPDATE SET attrib = EXCLUDED.attrib, path = EXCLUDED.path
             """
        )

        current_attrib_set: dict[str, Any] = {}
        buff: list[tuple[str, str, dict[str, Any]]] = []

        async for record in st_crawl.cursor():
            path_elements = record["path"].split("/")
            if len(path_elements) == 1:
                current_attrib_set = project_attrib.copy()

            new_attrib_set = current_attrib_set.copy()
            new_attrib_set.update(record["own"])

            if record["exported"] != new_attrib_set:
                # print()
                # print("Path:", record["path"])
                # print("Using", record["own"])
                # print(new_attrib_set)
                # print()
                buff.append(
                    (
                        record["id"],
                        record["path"],
                        new_attrib_set,
                    )
                )

            if len(buff) > 100:
                await st_upsert.executemany(buff)
                buff = []

            current_attrib_set = new_attrib_set

        if buff:
            await st_upsert.executemany(buff)
