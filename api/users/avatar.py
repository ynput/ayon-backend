from ayon_server.api.dependencies import CurrentUser

from .router import router


@router.get("/avatar")
async def get_avatar(user: CurrentUser):
    pass


@router.put("/avatar")
async def set_avatar(user: CurrentUser):
    pass
