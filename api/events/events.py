from typing import Any

from fastapi import APIRouter, Depends, Response

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_event_id
from openpype.entities import UserEntity
from openpype.events import EventModel, dispatch_event, update_event
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
    depends_on: str | None = Field(None, min_length=32, max_length=32)
    description: str = Field("")
    summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    finished: bool = True
    store: bool = True


class DispatchEventResponseModel(OPModel):
    id: str


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
            sender=record["sender"],
            depends_on=record["depends_on"],
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


class PatchEventRequestModel(OPModel):
    sender: str | None = None
    project_name: str | None = None
    status: str | None = None
    description: str | None = None
    summary: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


@router.patch("/events/{event_id}", response_class=Response)
async def patch_event(
    payload: PatchEventRequestModel,
    user: UserEntity = Depends(dep_current_user),
    event_id: str = Depends(dep_event_id),
):

    await update_event(
        event_id,
        payload.sender,
        payload.project_name,
        payload.status,
        payload.description,
        payload.summary,
        payload.payload,
    )

    return Response(status_code=204)


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
    id: str = Field(...)
    depends_on: str = Field(...)
    hash: str = Field(...)
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
            target_events.sender AS target_sender,
            target_events.hash AS target_hash,
            target_events.id AS target_id
        FROM
            events AS source_events
        LEFT JOIN
            events AS target_events
        ON target_events.depends_on = source_events.id

        WHERE
            source_events.topic = $1
        AND
            source_events.status = 'finished'
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

            print(sender, row["target_sender"])
            if row["target_sender"] != sender:
                if payload.sequential:
                    return Response(status_code=204)
                continue

            # TODO: handle restarting own jobs
            # if a job is restarted, just return its id so
            # the processor will
            return EnrollResponseModel(
                id=row["target_id"],
                depends_on=row["source_id"],
                status=row["target_status"],
                hash="target_hash",
            )

        # Target event does not exist yet. Create a new one
        new_hash = hash_data((payload.target_topic, row["source_id"]))
        new_id = await dispatch_event(
            payload.target_topic,
            sender=sender,
            hash=new_hash,
            depends_on=row["source_id"],
            user=current_user.name,
            description=description,
            finished=False,
        )

        if new_id:
            return EnrollResponseModel(
                id=new_id, hash=new_hash, depends_on=row["source_id"]
            )
        elif payload.sequential:
            return Response(status_code=204)

    return Response(status_code=204)
