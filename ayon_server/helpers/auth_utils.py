from typing import TYPE_CHECKING, Literal, Union

from ayon_server.exceptions import UnauthorizedException
from ayon_server.types import OPModel

if TYPE_CHECKING:
    from ayon_server.api.clientinfo import ClientInfo
    from ayon_server.entities import UserEntity


class UserPoolModel(OPModel):
    id: str
    title: str
    type: Literal["fixed", "metered"]
    valid: bool
    note: str
    exp: int
    max: int
    used: int


class AuthUtils:
    @staticmethod
    async def ensure_can_login(
        user: "UserEntity",
        client_info: Union["ClientInfo", None] = None,
        post_save: bool = False,
    ) -> None:
        """Ensure the user can log in.

        Raise UnauthorizedException if user is not allowed to log in.
        Return None otherwise.
        """

        if not user.active:
            raise UnauthorizedException("User is not active")

    @staticmethod
    async def get_user_pools() -> list[UserPoolModel]:
        """Return a list of user pools."""
        return []  # For future use
