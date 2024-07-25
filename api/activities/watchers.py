from fastapi import Header

from ayon_server.activities.watchers import get_watchers_list, set_watchers_list
from ayon_server.api.dependencies import (
    CurrentUser,
    PathEntityID,
    PathProjectLevelEntityType,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .router import router


class WatchersModel(OPModel):
    watchers: list[str] = Field(..., example=["user1", "user2"])


@router.get("/{entity_type}/{entity_id}/watchers")
async def get_entity_watchers(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
) -> WatchersModel:
    """Get watchers of an entity."""

    # TODO: ACL

    watchers = await get_watchers_list(project_name, entity_type, entity_id)

    return WatchersModel(watchers=watchers)


@router.post("/{entity_type}/{entity_id}/watchers", status_code=201)
async def set_entity_watchers(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
    watchers: WatchersModel,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    # TODO: ACL

    await set_watchers_list(
        project_name, entity_type, entity_id, watchers.watchers, sender=x_sender
    )

    return EmptyResponse()
