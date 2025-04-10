from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entity_lists.create_entity_list import (
    create_entity_list as _create_entity_list,
)
from ayon_server.entity_lists.create_list_item import (
    create_list_item as _create_list_item,
)
from ayon_server.entity_lists.delete_entity_list import (
    delete_entity_list as _delete_entity_list,
)
from ayon_server.entity_lists.materialize import (
    materialize_entity_list as _materialize_entity_list,
)
from ayon_server.entity_lists.models import (
    EntityListConfig,
    EntityListItemModel,
    EntityListModel,
    EntityListPatchModel,
)
from ayon_server.entity_lists.summary import (
    EntityListSummary,
    get_entity_list_summary,
    on_list_items_changed,
)
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

from .router import router


@router.post("", status_code=201)
async def create_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    payload: EntityListModel,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Create a new entity list.

    When passing list item, position field will be ignored and instead,
    the position will be determined by the order of the items in the list.
    """

    list_id = payload.id or create_uuid()

    if not payload.label:
        raise BadRequestException("Label is required")

    if not payload.entity_list_type:
        raise BadRequestException("Entity list type is required")

    config = payload.config if payload.config else EntityListConfig()

    async with Postgres.acquire() as conn, conn.transaction():
        await _create_entity_list(
            project_name,
            payload.entity_list_type,
            payload.label,
            id=list_id,
            template=payload.template,
            access=payload.access,
            attrib=payload.attrib,
            config=config,
            data=payload.data,
            tags=payload.tags,
            user=user,
            sender=sender,
            sender_type=sender_type,
            conn=conn,
        )

        if payload.items:
            for position, list_item in enumerate(payload.items):
                if list_item.entity_type not in config.entity_types:
                    raise BadRequestException(
                        f"Unsupported entity type: {list_item.entity_type}"
                    )

                await _create_list_item(
                    project_name,
                    list_id,
                    list_item.entity_type,
                    list_item.entity_id,
                    position=position,
                    id=list_item.id,
                    attrib=list_item.attrib,
                    data=list_item.data,
                    tags=list_item.tags,
                    user=user,
                    conn=conn,
                )
            summary = await on_list_items_changed(
                conn,
                project_name,
                list_id,
                user=user,
                sender=sender,
                sender_type=sender_type,
            )
        else:
            summary = await get_entity_list_summary(conn, project_name, list_id)

    return summary


@router.post("/{list_id}/materialize")
async def materialize_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Materialize an entity list."""

    return await _materialize_entity_list(
        project_name,
        list_id,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )


@router.patch("/{list_id}")
async def update_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    payload: EntityListPatchModel,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Update entity list metadata"""

    # TODO

    return EmptyResponse()


@router.get("/{list_id}")
async def get_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EntityListModel:
    """Get entity list

    This is for testing only. Since lists could be huge,
    it is not recommended to get them using this endpoint,

    Use GraphQL API to get the list items instead.
    """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
        q = "SELECT * FROM entity_lists WHERE id = $1"
        list_data = await conn.fetchrow(q, list_id)
        if list_data is None:
            raise NotFoundException(status_code=404, detail="List not found")

        result = EntityListModel(**dict(list_data), items=[])
        q = """
        SELECT * FROM entity_list_items
        WHERE entity_list_id = $1
        ORDER BY position ASC
        """
        statement = await conn.prepare(q)
        assert isinstance(result.items, list), "Items should be a list"
        async for row in statement.cursor(list_id):
            result.items.append(EntityListItemModel(**dict(row)))

    return result


@router.delete("/{list_id}")
async def delete_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EmptyResponse:
    """Delete entity list"""

    await _delete_entity_list(project_name, list_id, user=user)
    return EmptyResponse()
