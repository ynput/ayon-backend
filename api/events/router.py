from fastapi import APIRouter

from ayon_server.api import ResponseFactory

router = APIRouter(
    prefix="",
    tags=["Events"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)
