from typing import Literal

from nxtools import logging
from strawberry.types import Info

from ayon_server.graphql.nodes.common import LinkEdge, LinksConnection
from ayon_server.graphql.types import PageInfo
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool


async def get_links(
    root,
    info: Info,
    direction: Literal["in", "out"] | None,
    link_type: str,
    first: int,
    after: str | None,
) -> LinksConnection:

    project_name = root.project_name
    logging.info(f"Loading entities linked to entity {root.id} in {project_name}")

    edges: list[LinkEdge] = []

    sql_conditions = []
    if direction == "in":
        sql_conditions.append(f"output_id = '{root.id}'")
    elif direction == "out":
        sql_conditions.append(f"input_id = '{root.id}'")
    else:
        sql_conditions.append(f"(input_id = '{root.id}' or output_id = '{root.id}')")

    if after is not None and after.isdigit():
        sql_conditions.append(f"id > {after}")

    query = f"""
        SELECT id, input_id, output_id, link_name, data, created_at
        FROM project_{project_name}.links
        {SQLTool.conditions(sql_conditions)}
        ORDER BY creation_order
        LIMIT {first}
    """

    async for row in Postgres.iterate(query):
        if first <= len(edges):
            break

        link_type, input_type, output_type = row["link_name"].split("|")
        input_id = row["input_id"]
        output_id = row["output_id"]
        link_id = row["id"]

        if root.id == output_id:
            direction = "in"
            entity_id = input_id
            entity_type = input_type
        else:
            direction = "out"
            entity_id = output_id
            entity_type = output_type

        description = (
            f"{link_type} link with input {input_type} and output {output_type}"
        )

        edges.append(
            LinkEdge(
                id=row["id"],
                project_name=project_name,
                direction=direction,
                entity_id=entity_id,
                entity_type=entity_type,
                link_type=link_type,
                cursor=link_id,
                description=description,
                author=row["data"].get("author"),
            )
        )

    has_next_page = len(edges) >= first
    end_cursor = edges[-1].cursor if edges else None

    page_info = PageInfo(
        has_next_page=has_next_page,
        end_cursor=end_cursor,
    )

    return LinksConnection(edges=edges, page_info=page_info)
