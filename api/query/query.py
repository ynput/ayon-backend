from typing import Any, Literal

from fastapi import APIRouter

from ayon_server.api.dependencies import CurrentUser
from ayon_server.events import EventModel
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel

router = APIRouter(prefix="", tags=["Events"])


class QueryRequestModel(OPModel):
    entity: Literal[
        "event",
        "project",
        "user",
        "folder",
        "product",
        "task",
        "version",
        "representation",
        "workfile",
    ] = Field(...)
    filter: QueryFilter | None = Field(
        None, title="Filter", description="Filter events"
    )
    limit: int = Field(
        100, title="Limit", description="Maximum number of events to return"
    )
    offset: int = Field(
        0, title="Offset", description="Offset of the first event to return"
    )


@router.post("/query")
async def query(
    request: QueryRequestModel,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    if not current_user.is_admin:
        raise ForbiddenException("Only admins can use this endpoint")

    assert request.entity == "event", "Only events are supported for now"

    f = build_filter(request.filter, table_prefix="events") or "TRUE"

    query = f"""
        SELECT * FROM events
        WHERE {f}
        ORDER BY creation_order DESC
        LIMIT $1
        OFFSET $2
    """

    events = []
    async for record in Postgres.iterate(query, request.limit, request.offset):
        events.append(
            EventModel(
                id=record["id"],
                hash=record["hash"],
                topic=record["topic"],
                project=record["project_name"],
                user=record["user_name"],
                sender=record["sender"],
                sender_type=record["sender_type"],
                depends_on=record["depends_on"],
                status=record["status"],
                retries=record["retries"],
                description=record["description"],
                payload=record["payload"],
                summary=record["summary"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            ).dict(exclude_none=True, exclude_unset=True)
        )
    return events
