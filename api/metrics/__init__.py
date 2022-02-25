from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from openpype.lib.redis import Redis
from openpype.lib.postgres import Postgres


router = APIRouter(prefix="", include_in_schema=False)


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():

    result = ""
    async for record in Postgres.iterate("SELECT name FROM users"):
        name = record["name"]
        requests = await Redis.get("user-requests", name)
        if requests is None:
            requests = 0
        else:
            try:
                requests = int(requests.decode("utf-8"))
            except ValueError:
                requests = 0
        result += f"openpype_user_requests{{name=\"{name}\"}} {requests}\n"

    return PlainTextResponse(result)
