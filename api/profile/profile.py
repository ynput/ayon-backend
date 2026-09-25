from typing import Any

from ayon_server.api.dependencies import (
    AllowGuests,
    CurrentUser,
)
from ayon_server.auth.session import Session
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
)
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger

from .router import router

#
# [GET] /api/users/me
#


@router.get("", dependencies=[AllowGuests])
async def get_current_user_profile(
    user: CurrentUser,
) -> UserEntity.model.main_model:  # type: ignore
    """
    Return the current user information (based on the Authorization header).
    This is used for a profile page as well as as an initial check to ensure
    the user is still logged in.
    """

    payload = user.payload
    payload.ui_exposure_level = await user.get_ui_exposure_level()  # type: ignore
    payload.data.pop("supportToken", None)  # type: ignore
    return payload


async def update_guest_attrib(
    user: UserEntity, token: str, attrib_dict: dict[str, Any]
) -> None:
    if user.data.get("isProjectGuest"):
        # Project guest users are not allowed to update their profile
        raise BadRequestException("Project guest users cannot update their profile.")

    for key, value in attrib_dict.items():
        if key not in ["fullName", "avatarUrl", "email"]:
            raise BadRequestException(
                f"Cannot update attribute '{key}' for guest user."
            )
        setattr(user.attrib, key, value)

    await Session.update(token, user)


@router.patch("", dependencies=[AllowGuests])
async def update_current_user_profile(
    payload: UserEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
) -> None:

    attrib_dict = payload.attrib.dict(exclude_unset=True)

    session = user.session
    assert session is not None, "Session should be available for authenticated users"
    token = session.token
    assert token is not None, "Token should be available for authenticated users"

    if user.is_guest:
        await update_guest_attrib(user, token, attrib_dict)
        return

    target_user = await UserEntity.load(user.name)

    avatar_changed = False
    if (
        "avatarUrl" in attrib_dict
        and attrib_dict["avatarUrl"] != target_user.attrib.avatarUrl
    ):
        url = attrib_dict["avatarUrl"]
        if (url) and not (url.startswith("http://") or url.startswith("https://")):
            raise BadRequestException("Invalid avatar URL")
        avatar_changed = True

    for key, value in attrib_dict.items():
        setattr(target_user.attrib, key, value)

    await target_user.save()

    if avatar_changed:
        logger.debug(f"User {user.name} avatar changed, updating cache")
        await Redis.delete("user.avatar", user.name)

    return None
