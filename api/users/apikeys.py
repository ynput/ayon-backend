from ayon_server.api.dependencies import CurrentUser

from .router import router


@router.get("/apikeys")
def get_user_api_keys(user: CurrentUser):
    pass
