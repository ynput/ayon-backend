from fastapi import Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.auth.session import Session, SessionModel
from ayon_server.entities import UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import Field, OPModel

from .router import router


@router.get("/sessions")
async def list_active_sessions(user: CurrentUser) -> list[SessionModel]:
    if not user.is_manager:
        raise ForbiddenException()

    result: list[SessionModel] = []
    async for row in Session.list():
        result.append(row)

    return result


class CreateSessionRequest(OPModel):
    user_name: str | None = Field(None, description="User name to create session for")
    message: str | None = Field(None, description="Message to log in event stream")


@router.post("/sessions")
async def create_session(
    user: CurrentUser,
    request: Request,
    payload: CreateSessionRequest,
) -> SessionModel:
    """Create user session

    - services can use this endpoint to create a session for a user
    - users can use this endpoint to create additional sessions for themselves
      (e.g. to authenticate Ayon Launcher)
    """

    if payload.user_name and payload.user_name != user.name:
        if not user.is_service:
            raise ForbiddenException(
                "Only services can create sessions for other users"
            )
        target_user = await UserEntity.load(payload.user_name)
    else:
        target_user = user

    message = payload.message or f"Session created for {target_user.name}"
    if payload.user_name:
        message = f"{message} by {user.name}"

    return await Session.create(
        user=target_user,
        request=request,
        message=message,
    )
