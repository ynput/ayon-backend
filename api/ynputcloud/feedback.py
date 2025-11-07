from typing import Annotated, Any

import httpx

from ayon_server.api.dependencies import CurrentUser
from ayon_server.config import ayonconfig
from ayon_server.entities.user import UserEntity
from ayon_server.helpers.cloud import (
    CloudUtils,
)
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import OPModel
from ayon_server.version import __version__

from .router import router


class UserVerificationResponse(OPModel):
    available: bool = False
    detail: str | None = None
    data: dict[str, Any] | None = None


async def _get_feedback_verification(
    user: UserEntity,
    headers: dict[str, str],
    force: bool = False,
) -> UserVerificationResponse:
    if not force:
        if data := await Redis.get_json("feedback-verification", user.name):
            return UserVerificationResponse(**data)

    res = None
    payload = {
        "name": user.name,
        "email": user.attrib.email,
        "fullName": user.attrib.fullName or None,
        "avatarUrl": user.attrib.avatarUrl,
        "level": await user.get_ui_exposure_level(),
        "serverVersion": __version__,
    }

    try:
        url = f"{ayonconfig.ynput_cloud_api_url}/api/v2/feedback"
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            await Redis.set_json(
                "feedback-verification",
                user.name,
                {"available": True, "data": data},
                ttl=7200,
            )
            return UserVerificationResponse(available=True, data=data)
    except Exception as e:
        logger.trace(f"Feedback verification failed: {e}")
        if res is not None:
            try:
                detail = res.json()["detail"]
            except Exception:
                detail = res.text[:100]
        else:
            detail = str(e)
        await Redis.set_json(
            "feedback-verification",
            user.name,
            {"available": False, "detail": detail},
            ttl=600,
        )
        return UserVerificationResponse(available=False, detail=detail)


@router.get("/feedback")
async def get_feedback_verification(
    user: CurrentUser,
    force: Annotated[bool, "Force refresh of the feedback verification"] = False,
) -> UserVerificationResponse:
    """Verify feedback availability for the user and return verification data."""

    if user.is_guest:
        return UserVerificationResponse(
            available=False,
            detail="Guest users cannot send feedback.",
        )

    if ayonconfig.disable_feedback:
        return UserVerificationResponse(
            available=False,
            detail="Feedback is disabled on this server.",
        )

    # Get headers here to abort if not connected to the cloud
    try:
        headers = await CloudUtils.get_api_headers()
    except Exception:
        return UserVerificationResponse(
            available=False,
            detail="Not connected to Ynput Cloud.",
        )

    res = await _get_feedback_verification(user, headers, force)
    return res
