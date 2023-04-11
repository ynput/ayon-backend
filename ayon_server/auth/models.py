from pydantic import Field

from ayon_server.entities import UserEntity
from ayon_server.types import OPModel


class LoginResponseModel(OPModel):
    detail: str | None = Field(None, example="Logged in as NAME")
    error: str | None = Field(None, example="Unauthorized")
    token: str | None = Field(None, title="Access token", example="TOKEN")
    user: UserEntity.model.main_model | None = Field(  # type: ignore
        None,
        title="User data",
    )
