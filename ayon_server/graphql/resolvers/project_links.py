from typing import Any

from ayon_server.access.utils import AccessChecker
from ayon_server.graphql.nodes.common import ProjectLinkEdge, ProjectLinksConnection
from ayon_server.graphql.types import Info, PageInfo
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool


async def get_project_links(
    root,
    info: Info,
    ids: list[str] | None = None,
    entity_ids: list[str] | None = None,
    input_ids: list[str] | None = None,
    output_ids: list[str] | None = None,
    link_types: list[str] | None = None,
    input_types: list[str] | None = None,
    output_types: list[str] | None = None,
    first: int = 100,
    after: str | None = None,
    names: list[str] | None = None,
    name_ex: str | None = None,
) -> ProjectLinksConnection:
    """List all links in the project, with optional filters."""

    first = max(first, 0)

    project_name = root.project_name
    user = info.context["user"]
    if not user.is_manager:
        access_checker = AccessChecker()
        await access_checker.load(user, project_name)
        info.context["access_checker"] = access_checker

    args: list[Any] = []

    def next_idx():
        idx = len(args) + 1
        return f"${idx}"

    cte_conds = []
    if link_types:
        cte_conds.append(f"link_type = ANY({next_idx()})")
        args.append(link_types)
    if input_types:
        cte_conds.append(f"input_type = ANY({next_idx()})")
        args.append(input_types)
    if output_types:
        cte_conds.append(f"output_type = ANY({next_idx()})")
        args.append(output_types)

    sql_conditions = []

    if ids:
        sql_conditions.append(f"l.id = ANY({next_idx()})")
        args.append(ids)

    if entity_ids:
        idx = next_idx()
        sql_conditions.append(f"(l.input_id = ANY({idx}) OR l.output_id = ANY({idx}))")
        args.append(entity_ids)

    if input_ids:
        sql_conditions.append(f"l.input_id = ANY({next_idx()})")
        args.append(input_ids)

    if output_ids:
        sql_conditions.append(f"l.output_id = ANY({next_idx()})")
        args.append(output_ids)

    if after is not None and after.isdigit():
        sql_conditions.append(f"l.creation_order > {next_idx()}")
        args.append(int(after))

    if names:
        sql_conditions.append(f"l.name = ANY({next_idx()})")
        args.append(names)

    if name_ex:
        sql_conditions.append(f"l.name ~ {next_idx()}")
        args.append(name_ex)

    query = f"""
        WITH matching_link_types AS (
            SELECT name, input_type, output_type, link_type
            FROM project_{project_name}.link_types
            {SQLTool.conditions(cte_conds)}
        )

        SELECT
            l.id,
            l.name,
            l.input_id,
            l.output_id,
            l.author,
            l.data,
            l.created_at,
            l.creation_order,
            m.link_type,
            m.input_type,
            m.output_type

        FROM project_{project_name}.links l
        JOIN matching_link_types m ON l.link_type = m.name
        {SQLTool.conditions(sql_conditions)}
        ORDER BY creation_order
        LIMIT {first + 1}
    """

    edges: list[ProjectLinkEdge] = []

    async for row in Postgres.iterate(query, *args):
        input_id = row["input_id"]
        output_id = row["output_id"]
        cursor = str(row["creation_order"])
        input_type = row["input_type"]
        output_type = row["output_type"]
        link_type = row["link_type"]

        edges.append(
            ProjectLinkEdge(
                id=row["id"],
                input_id=input_id,
                output_id=output_id,
                input_type=input_type,
                output_type=output_type,
                project_name=project_name,
                name=row["name"],
                link_type=link_type,
                cursor=cursor,
                author=row["author"] if user.is_manager else None,
                created_at=row["created_at"],
                data=row["data"],
            )
        )

    has_next_page = len(edges) > first
    if has_next_page:
        edges = edges[:first]
    end_cursor = edges[-1].cursor if edges else None

    page_info = PageInfo(
        has_next_page=has_next_page,
        end_cursor=end_cursor,
    )

    return ProjectLinksConnection(edges=edges, page_info=page_info)
