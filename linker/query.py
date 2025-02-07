from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Literal

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool


@dataclass
class EntityResult:
    id: str
    folder_id: str
    version: int


async def query_entities(
    project_name: str,
    entity_type: str,
    folder_path: str | None = None,
    folder_type: str | None = None,
    folder_id: str | None = None,
    product_name: str | None = None,
    limit: int | None = None,
    version: Literal["hero", "latest"] | int | None = None,
) -> AsyncGenerator[EntityResult, None]:
    """Query entities from a project.

    Returns a generator of tuples of (folder_id, entity_id) for a
    given entity type and filters.
    """

    conditions = []

    if folder_id is not None:
        conditions.append(f"folder_id = '{folder_id}'")
    if folder_type is not None:
        conditions.append(f"folder_type = '{folder_type}'")
    if folder_path is not None:
        conditions.append(f"h.path ~* '{folder_path.strip('/')}'")
    if product_name is not None:
        conditions.append(f"s.name ~* '{product_name}'")

    if isinstance(version, int):
        conditions.append(f"v.version = {version}")
    elif version in ("hero", "latest"):
        # TODO: hero's not implemented yet
        conditions.append("v.id = l.ids[array_upper(l.ids, 1)]")

    if limit is not None:
        cols = ["f.id as folder_id", "s.id as product_id", "v.id as version_id"]
    else:
        if entity_type == "folder":
            cols = [
                "distinct(f.id) as folder_id",
                "s.id as product_id",
                "v.id as version_id",
            ]
        elif entity_type == "product":
            cols = [
                "distinct(s.id) as product_id",
                "f.id as folder_id",
                "v.id as version_id",
            ]
        elif entity_type == "version":
            cols = [
                "distinct(v.id) as version_id",
                "f.id as folder_id",
                "s.id as product_id",
            ]
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

    cols.extend(
        [
            "h.path as path",
            "s.name as product_name",
            "s.product_type as product_type",
            "v.version as version",
        ]
    )

    query = f"""
        SELECT {", ".join(cols)}
        FROM
            project_{project_name}.folders f
        INNER JOIN
            project_{project_name}.products s
            ON f.id = s.folder_id
        INNER JOIN
            project_{project_name}.versions v
            ON s.id = v.product_id
        INNER JOIN
            project_{project_name}.hierarchy h
            ON f.id = h.id
        INNER JOIN
            project_{project_name}.version_list l
            ON s.id = l.product_id
        {SQLTool.conditions(conditions)}
        {'ORDER BY RANDOM()' if limit is not None else ''}
    """

    used: list[str] = []  # faster that trying to find out, how to distinct
    async for row in Postgres.iterate(query):
        if row[f"{entity_type}_id"] in used:
            continue
        used.append(row[f"{entity_type}_id"])

        yield EntityResult(
            id=row[f"{entity_type}_id"],
            folder_id=row["folder_id"],
            version=row["version"],
        )
        if limit is not None and len(used) >= limit:
            break
