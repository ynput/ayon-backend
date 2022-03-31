from nxtools import logging
from strawberry.types import Info

from openpype.graphql.nodes.common import LinkEdge, LinksConnection
from openpype.lib.postgres import Postgres


async def get_links(
    root,
    info: Info,
) -> LinksConnection:

    project_name = root.project_name
    logging.info(f"Loading entities linked to entity {root.id} in {project_name}")

    edges = []

    def add_row(row, entity_type):
        edges.append(
            LinkEdge(
                project_name=project_name,
                entity_type=entity_type,
                entity_id=row["id"],
                link_type="steelchain",
                direction="nachuj",
                cursor=row["id"],
            )
        )

    async for row in Postgres.iterate(
        f"SELECT id FROM project_{project_name}.folders ORDER BY RANDOM() LIMIT 2"
    ):
        add_row(row, "folder")

    async for row in Postgres.iterate(
        f"SELECT id FROM project_{project_name}.versions ORDER BY RANDOM() LIMIT 2"
    ):
        add_row(row, "version")

    return LinksConnection(edges=edges)
