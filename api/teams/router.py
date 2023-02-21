from fastapi import APIRouter

from ayon_server.api import ResponseFactory

router = APIRouter(
    tags=["Teams"],
    prefix="/projects/{project_name}/teams",
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)
