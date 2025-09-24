from typing import Literal

from ayon_server.access.utils import AccessChecker
from ayon_server.graphql.nodes.common import LinkEdge, LinksConnection
from ayon_server.graphql.types import Info, PageInfo
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool


async def get_links(
    root,
    info: Info,
    direction: Literal["in", "out"] | None,
    link_types: list[str] | None,
    first: int = 100,
    after: str | None = None,
    names: list[str] | None = None,
    name_ex: str | None = None,
) -> LinksConnection:
    project_name = root.project_name
    user = info.context["user"]
    if not user.is_manager:
        access_checker = AccessChecker()
        await access_checker.load(user, project_name)
        info.context["access_checker"] = access_checker

    edges: list[LinkEdge] = []

    sql_conditions = []
    if direction == "in":
        sql_conditions.append(f"output_id = '{root.id}'")
    elif direction == "out":
        sql_conditions.append(f"input_id = '{root.id}'")
    else:
        sql_conditions.append(f"(input_id = '{root.id}' or output_id = '{root.id}')")

    type_conditions = []
    if link_types is not None:
        for lt in link_types:
            type_conditions.append(f"link_type LIKE '{lt}|%'")
        if type_conditions:
            sql_conditions.append(f"({' or '.join(type_conditions)})")

    if after is not None and after.isdigit():
        sql_conditions.append(f"creation_order > {after}")

    if names is not None:
        sql_conditions.append(f"name in {SQLTool.array(names)}")

    if name_ex is not None:
        sql_conditions.append(f"name ~ '{name_ex}'")

    query = f"""
        SELECT id, name, input_id, output_id, link_type, author, data, created_at
        FROM project_{project_name}.links
        {SQLTool.conditions(sql_conditions)}
        ORDER BY creation_order
        LIMIT {first}
    """

    async for row in Postgres.iterate(query):
        if first <= len(edges):
            break

        link_type, input_type, output_type = row["link_type"].split("|")
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
                name=row["name"],
                link_type=link_type,
                cursor=link_id,
                description=description,
                author=row["author"],
            )
        )

    has_next_page = len(edges) >= first
    end_cursor = edges[-1].cursor if edges else None

    page_info = PageInfo(
        has_next_page=has_next_page,
        end_cursor=end_cursor,
    )

    return LinksConnection(edges=edges, page_info=page_info)
