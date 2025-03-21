from ayon_server.graphql.nodes.entity_list import (
    EntityListItemEdge,
    EntityListItemsConnection,
)
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
)
from ayon_server.graphql.types import Info, PageInfo
from ayon_server.lib.postgres import Postgres


async def get_entity_list_items(
    root,
    info: Info,
    entity_list_id: str,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> EntityListItemsConnection:
    project_name = root.project_name

    edges: list[EntityListItemEdge] = []

    query = f"""
        SELECT *
        FROM project_{project_name}.entity_list_items
        WHERE entity_list_id = $1
        ORDER BY position ASC
    """

    async for row in Postgres.iterate(query, entity_list_id):
        item_id = row["id"]
        entity_type = row["entity_type"]
        entity_id = row["entity_id"]
        position = row["position"]

        attrib = row["attrib"]
        data = row["data"]
        tags = row["tags"]

        created_by = row["created_by"]
        updated_by = row["updated_by"]

        created_at = row["created_at"]
        updated_at = row["updated_at"]

        edges.append(
            EntityListItemEdge(
                id=item_id,
                project_name=project_name,
                entity_type=entity_type,
                entity_id=entity_id,
                position=position,
                attrib=attrib,
                data=data,
                tags=tags,
                created_by=created_by,
                updated_by=updated_by,
                created_at=created_at,
                updated_at=updated_at,
            )
        )

    page_info = PageInfo(
        has_next_page=False,
        end_cursor="noway",
    )

    return EntityListItemsConnection(edges=edges, page_info=page_info)
