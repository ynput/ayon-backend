from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ayon_server.api.clientinfo import ClientInfo
    from ayon_server.entities import UserEntity


class AuthHelper:
    @staticmethod
    async def ensure_can_login(
        user: "UserEntity",
        client_info: Union["ClientInfo", None] = None,
    ) -> None:
        """Ensure the user can log in. Raise an exception if not."""

        return None
