from ayon_server.activities.watchers.set_watchers import set_watchers
from ayon_server.activities.watchers.watcher_list import get_watcher_list
from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
    PathEntityID,
    PathProjectLevelEntityType,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import ForbiddenException
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.types import Field, OPModel

from .router import router


class WatchersModel(OPModel):
    watchers: list[str] = Field(..., example=["user1", "user2"])


@router.get("/{entity_type}/{entity_id}/watchers", dependencies=[AllowGuests])
async def get_entity_watchers(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
) -> WatchersModel:
    """Get watchers of an entity."""

    if user.is_guest:
        # Guests cannot see watchers, but we don't want to
        # throw 403 here
        return WatchersModel(watchers=[])

    entity_class = get_entity_class(entity_type)
    entity = await entity_class.load(project_name, entity_id)
    await entity.ensure_read_access(user)

    watchers = await get_watcher_list(entity)

    return WatchersModel(watchers=watchers)


@router.post(
    "/{entity_type}/{entity_id}/watchers", status_code=201, dependencies=[AllowGuests]
)
async def set_entity_watchers(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
    watchers: WatchersModel,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    if user.is_guest:
        # Guests cannot modify watchers
        raise ForbiddenException("Guests cannot modify watchers")

    entity_class = get_entity_class(entity_type)
    entity = await entity_class.load(project_name, entity_id)
    await entity.ensure_update_access(user)

    await set_watchers(
        entity,
        watchers.watchers,
        user,
        sender=sender,
        sender_type=sender_type,
    )

    return EmptyResponse()
