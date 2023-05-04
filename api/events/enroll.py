import json
from typing import Any, Literal, Union

from pydantic import Field

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.events import dispatch_event
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import Filter, build_filter
from ayon_server.types import OPModel
from ayon_server.utils import hash_data

from .router import router

#
# Enroll (get a new job)
#


class EnrollRequestModel(OPModel):
    source_topic: str = Field(
        ...,
        title="Source topic",
        example="ftrack.update",
    )
    target_topic: str = Field(
        ...,
        title="Target topic",
        example="ftrack.sync_to_ayon",
    )
    sender: str = Field(
        ...,
        title="Sender",
        example="workerservice01",
    )
    description: str | None = Field(
        None,
        title="Description",
        description="Short, human readable description of the target event",
        example="Sync Ftrack project to Ayon",
    )
    sequential: bool = Field(
        False,
        title="Sequential",
        description="Ensure events are processed in sequential order",
        example=True,
    )
    filter: Filter | None = Field(
        None, title="Filter", description="Filter source events"
    )
    debug: bool = False


class EnrollResponseModel(OPModel):
    id: str = Field(...)
    depends_on: str = Field(...)
    hash: str = Field(...)
    status: str = Field("pending")


# response model must be here
@router.post("/enroll", response_model=EnrollResponseModel)
async def enroll(
    payload: EnrollRequestModel,
    current_user: CurrentUser,
) -> EnrollResponseModel | EmptyResponse:
    """Enroll for a new job.

    Enroll for a new job by providing a source topic and target topic.
    Used by workers to get a new job to process. If there is no job
    available, request returns 204 (no content).

    Non-error response is returned because having nothing to do is not an error
    and we don't want to spam the logs.
    """
    sender = payload.sender

    if payload.description is None:
        description = f"Convert from {payload.source_topic} to {payload.target_topic}"
    else:
        description = payload.description

    filter = build_filter(payload.filter, table_prefix="source_events") or "TRUE"

    # Iterate thru unprocessed source events starting
    # by the oldest one

    query = f"""
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
            {filter}
        AND
            source_events.id NOT IN (
                SELECT depends_on
                FROM events
                WHERE topic = $2
                AND status in ('finished', 'failed')
            )

        ORDER BY source_events.created_at ASC
    """

    if payload.debug:
        print(query)
        print("source_topic", payload.source_topic)
        print("target_topic", payload.target_topic)

    async for row in Postgres.iterate(
        query, payload.source_topic, payload.target_topic
    ):
        if row["target_status"] is not None:
            if row["target_sender"] != sender:
                if payload.sequential:
                    return EmptyResponse()
                continue

            # TODO: handle restarting own jobs
            # if a job is restarted, just return its id so
            # the processor will
            return EnrollResponseModel(
                id=row["target_id"],
                depends_on=row["source_id"],
                status=row["target_status"],
                hash=row["target_hash"],
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
            return EmptyResponse()

    return EmptyResponse()
