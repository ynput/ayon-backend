from typing import Literal

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException, NotImplementedException
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel

from .router import router

OperationType = Literal["delete", "restart", "abort"]


class EventOperationModel(OPModel):
    type: OperationType = Field(..., title="Operation type")
    filter: QueryFilter = Field(..., title="Filter", description="Filter source events")


@router.post("/eventops")
async def event_operations(user: CurrentUser, request: EventOperationModel) -> None:
    if not user.is_admin:
        raise ForbiddenException("Only admins can perform event operations")

    filter_query = build_filter(request.filter) or "TRUE"

    if request.type == "delete":
        query = f"DELETE FROM events WHERE {filter_query}"
    else:
        raise NotImplementedException("Not implemented")

    await Postgres.execute(query)
