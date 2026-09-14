"""OAuth utilities for AYON Server."""

from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import UnauthorizedException
from ayon_server.oauth.storage import OAuthStorage


async def verify_oauth_token(token: str) -> UserEntity:
    """Verify OAuth access token and return user.

    Args:
        token (str): The OAuth access token to verify.

    Returns:
        UserEntity: The user associated with the OAuth token.

    Raises:
        UnauthorizedException: If the token is invalid or user not found.

    """
    token_data = await OAuthStorage.get_access_token(token)

    if not token_data:
        raise UnauthorizedException("Invalid OAuth token")

    # Load user entity
    user = await UserEntity.load(token_data["user_name"])
    if not user:
        raise UnauthorizedException("User not found")

    return user


async def get_oauth_token_info(token: str) -> dict[str, Any] | None:
    """Get OAuth token information.

    Args:
        token (str): The OAuth access token.

    Returns:
        dict[str, Any] | None: The token information if found, otherwise None.

    """
    return await OAuthStorage.get_access_token(token)


async def revoke_oauth_token(token: str) -> None:
    """Revoke OAuth access token."""
    await OAuthStorage.revoke_access_token(token)
