from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import ConstraintViolationException
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel
from ayon_server.utils import SQLTool, hash_data

SERVER_SENDER = "ayon_server"


class EnrollResponseModel(OPModel):
    id: str = Field(...)
    depends_on: str = Field(...)
    hash: str = Field(...)
    status: str = Field("pending")


async def enroll_job(
    source_topic: str | list[str],
    target_topic: str,
    *,
    sender: str | None = None,
    sender_type: str | None = None,
    user_name: str | None = None,
    description: str | None = None,
    sequential: bool = False,
    filter: QueryFilter | None = None,
    max_retries: int = 3,
    ignore_sender_types: list[str] | None = None,
    ignore_older_than: int | None = None,
    sloth_mode: bool = False,
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

    if isinstance(source_topic, str):
        topic_cond = "topic LIKE $1"
    else:
        topic_cond = "topic = ANY($1)"

    ignore_cond = ""
    if ignore_older_than is not None:
        ignore_cond = f"AND updated_at > NOW() - INTERVAL '{ignore_older_than} days'"

    sender_type_cond = ""
    if ignore_sender_types is not None:
        arr = SQLTool.array(ignore_sender_types)
        sender_type_cond = f"AND sender_type NOT IN {arr}"

    if sloth_mode:
        sloth_query = ", pg_sleep(0.2)"
    else:
        sloth_query = ""

    query = f"""
        WITH excluded_events AS (
            SELECT depends_on
            FROM public.events
            WHERE depends_on IS NOT NULL
            AND topic = $2
            {ignore_cond}
            AND (
                status = 'finished'
                OR (status = 'failed' AND retries > $3)
            )
        ),

        source_events AS (
            SELECT se.* {sloth_query}
            FROM public.events se
            LEFT JOIN excluded_events ee
                ON se.id = ee.depends_on
            WHERE {topic_cond}
            AND status = 'finished'
            {ignore_cond}
            {sender_type_cond}
            AND ee.depends_on IS NULL
        )

        SELECT
            source_events.id AS source_id,
            target_events.status AS target_status,
            target_events.sender AS target_sender,
            target_events.retries AS target_retries,
            target_events.hash AS target_hash,
            target_events.retries AS target_retries,
            target_events.id AS target_id
        FROM
            source_events
        LEFT JOIN events AS target_events
        ON
            target_events.depends_on = source_events.id
            AND target_events.topic = $2
        WHERE
            {filter_query}
        ORDER BY
            source_events.created_at ASC
        LIMIT 1000  -- Pool of 1000 events should be enough
    """

    async with Postgres.transaction():
        statement = await Postgres.prepare(query)
        async for row in statement.cursor(source_topic, target_topic, max_retries):
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
                        sender_type=sender_type,
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
            try:
                new_id = await EventStream.dispatch(
                    target_topic,
                    sender=sender,
                    sender_type=sender_type,
                    hash=new_hash,
                    depends_on=row["source_id"],
                    user=user_name,
                    description=description,
                    finished=False,
                )

            except ConstraintViolationException:
                # for some reason, the event already exists
                # most likely because another worker took it

                # in that case, we abort (if sequential) or
                # continue to the next event
                if sequential:
                    return None
                continue

            return EnrollResponseModel(
                id=new_id,
                hash=new_hash,
                depends_on=row["source_id"],
                status="pending",
            )

    return None
