from typing import Literal

from nxtools import logging
from strawberry.types import Info

from openpype.graphql.nodes.common import LinkEdge, LinksConnection
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool


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

    edges = []

    sql_conditions = []
    if direction == "in":
        sql_conditions.append(f"output_id = '{root.id}'")
    elif direction == "out":
        sql_conditions.append(f"input_id = '{root.id}'")
    else:
        sql_conditions.append(f"(input_id = '{root.id}' or output_id = '{root.id}')")

    if after is not None:
        sql_conditions.append("id > '{after}'")

    query = f"""
        SELECT id, input_id, output_id, link_name, data, created_at
        FROM project_{project_name}.links
        {SQLTool.conditions(sql_conditions)}
        ORDER BY id
        LIMIT {first}
    """

    async for row in Postgres.iterate(query):
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

    return LinksConnection(edges=edges)
