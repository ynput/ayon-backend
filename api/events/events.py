import uuid
from typing import Any

from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_event_id
from openpype.entities import UserEntity
from openpype.events import EventModel, dispatch_event
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel
from openpype.utils import hash_data

#
# Router
#

router = APIRouter(
    prefix="",
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
    depends_on: uuid.UUID | None = Field(None)
    description: str = Field("")
    summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    finished: bool = True
    store: bool = True


class DispatchEventResponseModel(OPModel):
    id: uuid.UUID


@router.post("/events", response_model=DispatchEventResponseModel)
async def post_event(
    request: DispatchEventRequestModel,
    user: UserEntity = Depends(dep_current_user),
) -> DispatchEventResponseModel:
    event_id = await dispatch_event(
        request.topic,
        sender=request.sender,
        hash=request.hash,
        user=user.name,
        # TODO description
        description=request.description,
        summary=request.summary,
        payload=request.payload,
        finished=request.finished,
        store=request.store,
    )
    return DispatchEventResponseModel(id=event_id)


@router.get("/events/{event_id}")
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
            payload=record["payload"],
            summary=record["summary"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
        break

    if event is None:
        raise NotFoundException("Event not found")
    return event


#
# Enroll (get a new job)
#


class EnrollRequestModel(OPModel):
    source_topic: str = Field(..., example="ftrack.update")
    target_topic: str = Field(..., example="ftrack.sync_to_openpype")
    sender: str = Field(..., example="workerservice01")
    description: str | None = Field(
        None,
        description="Short, human readable description of the target event",
    )
    sequential: bool = Field(
        False,
        description="Ensure events are processed in sequential order",
    )


class EnrollResponseModel(OPModel):
    id: uuid.UUID = Field(...)
    status: str = Field("pending")


@router.post("/enroll", response_model=EnrollResponseModel)
async def enroll(
    payload: EnrollRequestModel,
    current_user: UserEntity = Depends(dep_current_user),
):
    sender = payload.sender

    if payload.description is None:
        description = f"Convert from {payload.source_topic} to {payload.target_topic}"
    else:
        description = payload.description

    # Iterate thru unprocessed source events starting
    # by the oldest one

    async for row in Postgres.iterate(
        """
        SELECT
            source_events.id AS source_id,
            target_events.status AS target_status,
            target_events.sender AS target_sender
            target_events.id AS target_id
        FROM
            events AS source_events
        LEFT JOIN
            events AS target_events
        ON target_events.depends_on = source_events.id

        WHERE
            source_event.topic = $1
        AND
            source_event.status = 'finished'
        AND
            source_events.id NOT IN (
                SELECT depends_on
                FROM events
                WHERE topic = $2
                AND status in ('finished')
            )

        ORDER BY source_events.created_at ASC
        """,
        payload.source_topic,
        payload.target_topic,
    ):

        if row["target_status"] is not None:

            if row["target_sender"] != sender:
                if payload.sequential:
                    raise NotFoundException("Nothing to do")
                continue

            # TODO: handle restarting own jobs
            # if a job is restarted, just return its id so
            # the processor will
            return row["target_id"]
            return EnrollResponseModel(id=row["target_id"], status=row["target_status"])

        # Target event does not exist yet. Create a new one
        new_hash = hash_data((payload.target_topic, row["source_id"]))
        new_id = dispatch_event(
            payload.target_topic,
            sender=sender,
            hash=new_hash,
            depends_on=row["source_id"],
            user=current_user.name,
            description=description,
            finished=False,
        )

        if new_id:
            return EnrollResponseModel(id=new_id)
        elif payload.sequential:
            raise NotFoundException("Sequential booo")

    raise NotFoundException("Nothing to do")
