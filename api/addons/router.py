from fastapi import APIRouter

from openpype.api import ResponseFactory

router = APIRouter(
    prefix="/addons",
    tags=["Addon settings"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)
