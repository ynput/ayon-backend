import time

from fastapi import APIRouter

from ayon_server.api import ResponseFactory
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

#
# Router
#


router = APIRouter(
    prefix="/usd",
    tags=["USD"],
)

#
# [POST] /usd/resolve
#


class ResolveRequestModel(OPModel):
    uris: list[str] = Field(..., description="list of uris to resolve")


class ResolveResponseModel(OPModel):
    paths: list[str]
    time: float


@router.post(
    "/resolve",
    responses={401: ResponseFactory.error(401, "Unable to log in")},
)
async def resolve(request: ResolveRequestModel):

    start_time = time.monotonic()

    query = """
        SELECT r.attrib->>'path'
        FROM hierarchy as n
        INNER JOIN subsets AS s ON n.id = s.folder_id
        INNER JOIN versions AS v ON s.id = v.subset_id
        INNER JOIN representations AS r ON v.id = r.version_id
        WHERE
            n.path = $1
        AND s.name = $2
        AND v.version = $3
        AND r.name = $4
    """

    result = []
    current_project = ""
    async with Postgres.acquire() as conn:
        async with conn.transaction():
            for uri in request.uris:
                uri = uri.replace("op://", "", 1)
                path, args = uri.split("?")

                project, hpath = path.split("/", 1)
                subset = None
                version = None
                representation = None

                for elm in args.split("&"):
                    key, val = elm.split("=")
                    if key == "subset":
                        subset = val
                    elif key == "version":
                        version = int(val.lower().lstrip("v"))
                    elif key == "representation":
                        representation = val

                if project != current_project:
                    await conn.execute(f"SET LOCAL search_path TO project_{project}")
                    stmt = await conn.prepare(query)
                    current_project = project

                result.append(
                    await stmt.fetchval(hpath, subset, version, representation)
                )

    elapsed = time.monotonic() - start_time
    return {"paths": result, "time": elapsed}
