from fastapi import APIRouter

from ayon_server.api.responses import ResponseFactory

router = APIRouter(
    tags=["Representations"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)
