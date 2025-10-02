from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entity_lists.entity_list import EntityList
from ayon_server.entity_lists.models import (
    EntityListModel,
    EntityListPatchModel,
    EntityListPostModel,
    EntityListSummary,
)
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid, dict_patch

from .router import router


@router.post("/lists", status_code=201)
async def create_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    payload: EntityListPostModel,
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

    async with Postgres.transaction():
        entity_list = await EntityList.construct(
            project_name,
            payload.entity_type,
            payload.label,
            id=list_id,
            entity_list_type=payload.entity_list_type,
            entity_list_folder_id=payload.entity_list_folder_id,
            template=payload.template,
            access=payload.access,
            attrib=payload.attrib,
            active=payload.active if payload.active is not None else True,
            owner=payload.owner,
            data=payload.data,
            tags=payload.tags,
            user=user,
        )

        for item in payload.items:
            await entity_list.add(
                item.entity_id,
                id=item.id,
                position=item.position,
                label=item.label,
                attrib=item.attrib,
                data=item.data,
                tags=item.tags,
            )

        return await entity_list.save(sender=sender, sender_type=sender_type)


@router.patch("/lists/{list_id}")
async def update_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    payload: EntityListPatchModel,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Update entity list metadata"""

    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_admin()

        payload_dict = payload.dict(exclude_unset=True)

        for key, value in payload_dict.items():
            if not hasattr(entity_list.payload, key):
                continue
            if isinstance(value, dict) and key != "access":
                nval = dict_patch(getattr(entity_list.payload, key), value)
                setattr(entity_list.payload, key, nval)
            else:
                setattr(entity_list.payload, key, value)

        await entity_list.save(sender=sender, sender_type=sender_type)

    return EmptyResponse()


@router.get("/lists/{list_id}")
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

    entity_list = await EntityList.load(project_name, list_id, user=user)
    # we don't need to check for permissions here,
    # as this is handled in the load method
    return entity_list.payload


@router.delete("/lists/{list_id}")
async def delete_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
) -> EmptyResponse:
    """Delete entity list from the database"""

    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_admin()
        await entity_list.delete()

    return EmptyResponse()


@router.post("/lists/{list_id}/materialize")
async def materialize_entity_list(
    user: CurrentUser,
    project_name: ProjectName,
    list_id: str,
    sender: Sender,
    sender_type: SenderType,
) -> EntityListSummary:
    """Materialize an entity list."""

    async with Postgres.transaction():
        entity_list = await EntityList.load(project_name, list_id, user=user)
        await entity_list.ensure_can_admin()
        await entity_list.materialize()
        return await entity_list.save(sender=sender, sender_type=sender_type)
