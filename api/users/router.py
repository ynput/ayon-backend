from fastapi import APIRouter

from ayon_server.api.responses import ResponseFactory

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={401: ResponseFactory.error(401)},
)
