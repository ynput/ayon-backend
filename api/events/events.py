import uuid

from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_event_id
from openpype.entities import UserEntity
from openpype.events import EventModel
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.types import OPModel, Field

#
# Router
#

router = APIRouter(
    prefix="/events",
    tags=["Events"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class DispatchEventRequestModel(OPModel):
    topic: str = Field(...)
    sender: str | None = None
    hash: str | None = None
    project: str | None = None
    dependencies: list[uuid.UUID] | None = None
    description: str | None = None
    summary: dict | None = None
    payload: dict | None = None
    finished: bool = True
    store: bool = True


class DispatchEventResponseModel(OPModel):
    id: uuid.UUID


@router.post("", response_model=DispatchEventResponseModel)
async def dispatch_event(
    request: DispatchEventRequestModel,
    user: UserEntity = Depends(dep_current_user),
) -> DispatchEventResponseModel:
    event_id = await dispatch_event(**request, user=user.name)
    return DispatchEventRequestModel(id=event_id)


@router.get("/{event_id}")
async def get_event(
    user: UserEntity = Depends(dep_current_user),
    event_id: str = Depends(dep_event_id),
) -> EventModel:

    query = "SELECT * FROM events WHERE id = $1", event_id

    event: EventModel | None = None
    async for record in Postgres.iterate(*query):
        event = EventModel(
            id=record["id"],
            hash=record["hash"],
            topic=record["topic"],
            project=record["project_name"],
            user=record["user_name"],
            status=record["status"],
            retries=record["retries"],
            description=record["description"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
        break

    if event is None:
        raise NotFoundException("Event not found")
    return event
