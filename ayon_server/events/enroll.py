from ayon_server.events.eventstream import EventStream
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import Filter, build_filter
from ayon_server.types import Field, OPModel
from ayon_server.utils import hash_data

SERVER_SENDER = "ayon_server"


class EnrollResponseModel(OPModel):
    id: str = Field(...)
    depends_on: str = Field(...)
    hash: str = Field(...)
    status: str = Field("pending")


async def enroll_job(
    source_topic: str,
    target_topic: str,
    *,
    sender: str | None = None,
    user_name: str | None = None,
    description: str | None = None,
    sequential: bool = False,
    filter: Filter | None = None,
    max_retries: int = 3,
) -> EnrollResponseModel | None:
    if description is None:
        description = f"Convert from {source_topic} to {target_topic}"

    if sender is None:
        sender = SERVER_SENDER

    if user_name is None:
        sender = "server"

    filter_query = build_filter(filter, table_prefix="source_events") or "TRUE"

    # Iterate thru unprocessed source events starting
    # by the oldest one

    query = f"""
        SELECT
            source_events.id AS source_id,
            target_events.status AS target_status,
            target_events.sender AS target_sender,
            target_events.retries AS target_retries,
            target_events.hash AS target_hash,
            target_events.retries AS target_retries,
            target_events.id AS target_id
        FROM
            events AS source_events
        LEFT JOIN
            events AS target_events
        ON
            target_events.depends_on = source_events.id
            AND target_events.topic = $2

        WHERE
            source_events.topic ILIKE $1
        AND
            source_events.status = 'finished'
        AND
            {filter_query}
        AND
            source_events.id NOT IN (
                SELECT depends_on
                FROM events
                WHERE topic = $2
                AND (

                    -- skip events that are already finished

                    status = 'finished'

                    -- skip events that are already failed and have
                    -- reached max retries

                    OR (status = 'failed' AND retries > $3)
                )
            )

        ORDER BY source_events.created_at ASC
    """
    async for row in Postgres.iterate(
        query,
        source_topic,
        target_topic,
        max_retries,
    ):
        # Check if target event already exists
        if row["target_status"] is not None:
            if row["target_status"] in ["failed", "restarted"]:
                # events which have reached max retries are already
                # filtered out by the query above,
                # so we can just retry them - update status to pending
                # and increase retries counter

                retries = row["target_retries"]
                if row["target_status"] == "failed":
                    retries += 1

                event_id = row["target_id"]
                await EventStream.update(
                    event_id,
                    status="pending",
                    sender=sender,
                    user=user_name,
                    retries=retries,
                    description="Restarting failed event",
                )
                return EnrollResponseModel(
                    id=event_id,
                    hash=row["target_hash"],
                    depends_on=row["source_id"],
                    status="pending",
                )

            if row["target_sender"] != sender:
                # There is already a target event for this source event.
                # Check who is the sender. If it's not us, then we can't
                # enroll for this job (the other worker is already working on it)
                if sequential:
                    return None
                continue

            # We are the sender of the target event, so it is possible that,
            # for some reason, we have not finished processing it yet.
            # In this case, we can't enroll for this job again.

            return EnrollResponseModel(
                id=row["target_id"],
                depends_on=row["source_id"],
                status=row["target_status"],
                hash=row["target_hash"],
            )

        # Target event does not exist yet. Create a new one
        new_hash = hash_data((target_topic, row["source_id"]))
        new_id = await EventStream.dispatch(
            target_topic,
            sender=sender,
            hash=new_hash,
            depends_on=row["source_id"],
            user=user_name,
            description=description,
            finished=False,
        )

        if new_id:
            return EnrollResponseModel(
                id=new_id,
                hash=new_hash,
                depends_on=row["source_id"],
                status="pending",
            )
        elif sequential:
            return None

    return None
